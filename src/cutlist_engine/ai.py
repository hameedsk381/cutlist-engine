"""AI-powered features for the cutlist engine using Groq.

Three capabilities:
  1. label_parts()       — Auto-name boards from dimensions + source objects
  2. describe_to_cutlist() — Natural language → structured cutlist JSON
  3. chat()              — Context-aware workshop assistant
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_FAST = "meta-llama/llama-4-scout-17b-16e-instruct"
_MODEL_CHAT = "meta-llama/llama-4-scout-17b-16e-instruct"


def _client() -> Any:
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError(
            "AI features require the optional Groq client. "
            "Install it with: python -m pip install -e .[ai]"
        ) from exc

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set. "
            "Get a free key at https://console.groq.com/keys"
        )
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# 1. Smart Part Naming
# ---------------------------------------------------------------------------

_LABEL_SYSTEM = """\
You are an Indian furniture and modular cabinetry expert. Given a list of boards extracted from a 3D model, 
assign each board a clear, human-readable label that a carpenter would recognise on an Indian shop floor.

Rules:
- Use common Indian woodworking terminology (Pooja Unit Panel, Loft Top, Wardrobe Shutter, Skirting, Carcass Side, Backer, Laminate Board, etc.)
- If source_objects hint at the component name, use that context.
- If multiple boards share identical dimensions, differentiate them (Left Side, Right Side, Shelf 1, Shelf 2).
- Keep labels SHORT (2-4 words max).
- Respond with a JSON object: {"labels": {"board_id": "Human Label", ...}}
- Do NOT add any explanation, only the JSON object.
"""


def label_parts(boards: list[dict[str, Any]]) -> dict[str, str]:
    """Auto-name boards using LLM inference.

    Args:
        boards: list of board dicts with keys: id, length, width, thickness,
                source_objects, confidence

    Returns:
        dict mapping board_id -> human-readable label
    """
    # Build a compact prompt — only send what the LLM needs
    compact = []
    for b in boards:
        entry = {
            "id": b["id"],
            "length_mm": round(b.get("length", 0)),
            "width_mm": round(b.get("width", 0)),
            "thickness_mm": b.get("thickness", 18),
        }
        src = b.get("source_objects", [])
        if src:
            entry["source_objects"] = src[:3]  # limit context
        compact.append(entry)

    user_msg = json.dumps(compact, indent=None)

    try:
        resp = _client().chat.completions.create(
            model=_MODEL_FAST,
            messages=[
                {"role": "system", "content": _LABEL_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        result = json.loads(content)
        return result.get("labels", {})
    except Exception as e:
        logger.error("AI labeling failed: %s", e)
        raise


# ---------------------------------------------------------------------------
# 2. Natural Language → Cutlist
# ---------------------------------------------------------------------------

_DESCRIBE_SYSTEM = """\
You are an expert in the Indian modular kitchen and wardrobe industry. The user will describe a piece of furniture
in natural language. Convert it into a precise cutlist suitable for Indian manufacturing standards.

Rules:
- Calculate all panel dimensions using standard Indian joinery (e.g., 75mm skirting, 18mm plywood carcass, 6mm back panel).
- Use metric (mm) for all dimensions.
- Common items: Pooja Units, Modular Kitchen cabinets, Lofts, Wardrobe shutters with 2mm PVC edge banding.
- Internal width = external width - (2 × side panel thickness)
- Shelf depth is typically 20mm less than carcass depth.
- Respond ONLY with a JSON object in this exact format:

{
  "boards": [
    {"label": "Shutter A", "length": 720, "width": 450, "thickness": 18, "quantity": 2, "grain_locked": true, "edge_band": [2,2,2,2], "material": "Plywood", "priority": "visible"},
    ...
  ],
  "material_name": "18mm BWP Marine Plywood",
  "sheet_width": 2440,
  "sheet_height": 1220,
  "currency": "INR",
  "notes": "Brief design notes for Indian workshop standards"
}

- length = longest dimension, width = shortest dimension
- All dimensions in mm
- Respond with JSON only.
"""


def describe_to_cutlist(
    description: str,
    thickness: float = 18.0,
    sheet_width: float = 2440.0,
    sheet_height: float = 1220.0,
) -> dict[str, Any]:
    """Convert a natural language furniture description to a structured cutlist.

    Returns:
        dict with keys: boards, material_name, sheet_width, sheet_height, notes
    """
    user_msg = (
        f"Material thickness: {thickness}mm\n"
        f"Sheet size: {sheet_width}×{sheet_height}mm\n\n"
        f"Description:\n{description}"
    )

    try:
        resp = _client().chat.completions.create(
            model=_MODEL_FAST,
            messages=[
                {"role": "system", "content": _DESCRIBE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        result = json.loads(content)

        # Validate minimal structure
        if "boards" not in result or not isinstance(result["boards"], list):
            raise ValueError("LLM response missing 'boards' array")
        for board in result["boards"]:
            if not all(k in board for k in ("label", "length", "width")):
                raise ValueError(f"Board missing required fields: {board}")

        return result
    except json.JSONDecodeError as e:
        logger.error("AI describe response was not valid JSON: %s", e)
        raise ValueError(f"AI returned invalid JSON: {e}")
    except Exception as e:
        logger.error("AI describe failed: %s", e)
        raise


# ---------------------------------------------------------------------------
# 3. Workshop Chat Assistant
# ---------------------------------------------------------------------------

_CHAT_SYSTEM = """\
You are a helpful woodworking and cabinetry assistant embedded in a cutlist optimization tool.
You have access to the current project context (cutlist, sheets, material summary).

Rules:
- Answer questions about the current project using the provided context.
- Give practical, actionable advice a carpenter can use on the shop floor.
- Use metric (mm) for all dimensions.
- Be concise — carpenters are busy.
- If asked to modify the cutlist, explain what changes to make but clarify you cannot
  directly edit it (the user should re-upload or use the override system).
- When doing calculations (material needed for N copies, etc.), show your working.
- If the context is empty (no project loaded), still answer general woodworking questions.
"""


def chat(
    message: str,
    context: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Context-aware workshop chat.

    Args:
        message: User's question
        context: Current project data (cutlist, sheets, material_summary, boards)
        history: Previous chat messages [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        Assistant's response text
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": _CHAT_SYSTEM}]

    # Inject project context as a system message
    if context:
        ctx_summary = _build_context_summary(context)
        messages.append({
            "role": "system",
            "content": f"Current project context:\n{ctx_summary}",
        })

    # Add conversation history
    if history:
        messages.extend(history[-10:])  # keep last 10 exchanges

    messages.append({"role": "user", "content": message})

    try:
        resp = _client().chat.completions.create(
            model=_MODEL_CHAT,
            messages=messages,
            temperature=0.4,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or "I couldn't generate a response."
    except Exception as e:
        logger.error("AI chat failed: %s", e)
        raise


def _build_context_summary(context: dict[str, Any]) -> str:
    """Build a compact text summary of the current project for the LLM."""
    parts = []

    ms = context.get("material_summary", {})
    if ms:
        parts.append(
            f"Material: {ms.get('sheet_count', '?')} sheets, "
            f"{ms.get('utilization_percent', '?')}% utilization, "
            f"{ms.get('waste_percent', '?')}% waste, "
            f"reusable offcuts: {ms.get('reusable_offcut_area', 0):.2f} sq m, "
            f"cost: {ms.get('currency', 'INR')} {ms.get('total_material_cost', 0):.2f}"
        )

    cutlist = context.get("cutlist", [])
    if cutlist:
        lines = []
        for item in cutlist[:20]:  # limit to 20 items
            label = ""
            if item.get("labels"):
                label = item["labels"][0] if isinstance(item["labels"], list) else str(item["labels"])
            name = label or item.get("id", "?")
            lines.append(
                f"  {name}: {round(item.get('length', 0))}×{round(item.get('width', 0))}×"
                f"{item.get('thickness', '?')}mm qty={item.get('quantity', 1)} "
                f"material={item.get('material', 'default')}"
            )
        parts.append("Cutlist:\n" + "\n".join(lines))

    sheets = context.get("sheets", [])
    if sheets:
        sheet_lines = []
        for s in sheets[:10]:
            part_count = len(s.get("parts", []))
            sheet_lines.append(
                f"  Sheet {s.get('sheet_id', '?')}: "
                f"{round(s.get('width', 0))}×{round(s.get('height', 0))}mm, "
                f"{part_count} parts, "
                f"util={s.get('utilization_percent', '?')}%, "
                f"waste={s.get('waste_percent', '?')}%"
            )
        parts.append("Sheets:\n" + "\n".join(sheet_lines))

        # Include offcut details
        for s in sheets[:10]:
            offcuts = [o for o in s.get("offcuts", []) if o.get("reusable")]
            if offcuts:
                for o in offcuts:
                    parts.append(
                        f"  Sheet {s.get('sheet_id')}: reusable offcut "
                        f"{round(o.get('width', 0))}×{round(o.get('height', 0))}mm"
                    )

    return "\n".join(parts) if parts else "No project loaded."


# ---------------------------------------------------------------------------
# 4. Expert Suggestions
# ---------------------------------------------------------------------------

_SUGGEST_SYSTEM = """\
You are an expert furniture manufacturer and modular kitchen engineer in India. 
Analyze the following cutlist and nesting results. 
Provide 3-5 concise, high-impact suggestions focused on Indian manufacturing practices (Plywood, Laminate, Edge Banding).

Focus on:
1. Optimization: Can we save a 8x4 sheet (2440x1220mm)?
2. Quality: Suggest BWP/BWR plywood for wet areas (kitchen/bath).
3. Assembly: Suggest hardware (Hettich/Hafele/Ebco) or joinery tips.
4. Finishing: PVC edge banding (0.5mm vs 2mm) or laminate grain matching.

Format: Provide a list of bullet points. Keep it professional and brief.
"""


def suggest_improvements(context: dict[str, Any]) -> str:
    """Analyze results and provide expert advice."""
    ctx_summary = _build_context_summary(context)
    try:
        resp = _client().chat.completions.create(
            model=_MODEL_FAST,
            messages=[
                {"role": "system", "content": _SUGGEST_SYSTEM},
                {"role": "user", "content": f"Project Results:\n{ctx_summary}"},
            ],
            temperature=0.4,
            max_tokens=1024,
        )
        return resp.choices[0].message.content or "No specific suggestions at this time."
    except Exception as e:
        logger.error("AI suggestion failed: %s", e)
        return "Expert suggestions temporarily unavailable."
