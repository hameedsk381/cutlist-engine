"""The AI layer. Every call to a language model goes through this file.

Ground rule: a model reads and writes language, code does the arithmetic.
Models are used to
  - read a furniture description in any language into parameters,
  - read a photo of a hand sketch into the same parameters,
  - turn speech into text,
  - name parts, and
  - answer questions about a plan and *propose* changes to it.
They never produce panel sizes, sheet counts or prices. Those come from
`furniture.py`, the nesting engine and `saas/quote.py`, and every proposed
change is validated in code and applied only when the user confirms it.

Provider: Groq (https://console.groq.com). Model ids are read from the
environment so a retired model can be replaced without a code change:

  CUTLIST_AI_MODEL          text and JSON   (default openai/gpt-oss-120b)
  CUTLIST_AI_VISION_MODEL   image input     (default qwen/qwen3.8-27b)
  CUTLIST_AI_SPEECH_MODEL   speech to text  (default whisper-large-v3-turbo)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TEXT_MODEL = "openai/gpt-oss-120b"
DEFAULT_VISION_MODEL = "qwen/qwen3.8-27b"
DEFAULT_SPEECH_MODEL = "whisper-large-v3-turbo"

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

LANGUAGES = {
    "en": "English",
    "hi": "Hindi in Devanagari script, in simple workshop words. Keep part names, numbers and units exactly as given",
}


class AIError(RuntimeError):
    """An AI call could not be completed. The message is safe to show a user."""


def text_model() -> str:
    return os.environ.get("CUTLIST_AI_MODEL") or DEFAULT_TEXT_MODEL


def vision_model() -> str:
    return os.environ.get("CUTLIST_AI_VISION_MODEL") or DEFAULT_VISION_MODEL


def speech_model() -> str:
    return os.environ.get("CUTLIST_AI_SPEECH_MODEL") or DEFAULT_SPEECH_MODEL


def llm_available() -> bool:
    if not os.environ.get("GROQ_API_KEY"):
        return False
    try:
        import groq  # noqa: F401
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    return {
        "available": llm_available(),
        "text_model": text_model(),
        "vision_model": vision_model(),
        "speech_model": speech_model(),
    }


def _client() -> Any:
    try:
        from groq import Groq
    except ImportError as exc:
        raise AIError(
            "AI features require the optional Groq client. "
            "Install it with: python -m pip install -e .[ai]"
        ) from exc

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise AIError(
            "GROQ_API_KEY environment variable is not set. "
            "Get a free key at https://console.groq.com/keys"
        )
    return Groq(api_key=api_key, timeout=45.0)


def _complete(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    json_mode: bool = False,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    kwargs: dict[str, Any] = {
        "model": model or text_model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    client = _client()
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - provider errors vary by SDK version
        logger.error("AI request failed (%s): %s", kwargs["model"], exc)
        raise AIError("The AI service did not answer. Try again in a moment.") from exc
    choice = resp.choices[0]
    content = choice.message.content or ""
    if not content.strip():
        # Without this a blank answer looks like "the AI understood nothing".
        logger.warning(
            "AI answer was empty (model=%s, finish_reason=%s, max_tokens=%s)",
            kwargs["model"], getattr(choice, "finish_reason", "?"), max_tokens,
        )
    return content


def _loads(content: str) -> dict[str, Any]:
    """Parse a model's JSON answer, tolerating code fences and stray prose."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# 1. Description or sketch -> furniture parameters (never panel sizes)
# ---------------------------------------------------------------------------

_PARAM_KEYS = """\
{"kind": "wardrobe|tall_unit|base_cabinet|wall_cabinet|loft|bookshelf|cabinet",
 "height": <mm>, "width": <mm>, "depth": <mm>,
 "shelves": <int>, "shutters": <int>, "drawers": <int>, "partitions": <int>,
 "thickness": <board thickness in mm>, "plinth": <skirting height in mm>}"""

_PARAMS_SYSTEM = f"""\
You read a description of ONE piece of cabinet furniture and extract its
overall parameters. The text may be in English, Hindi, Hinglish, Telugu, Tamil,
Marathi or any other language, in any script, and may come from speech, so
expect spelling mistakes. Do NOT calculate any panel sizes.

Respond ONLY with a JSON object using these keys, omitting every key the text
does not state:

{_PARAM_KEYS}

Rules:
- Convert feet, inches, cm and metres to mm (1 ft = 304.8 mm, 1 in = 25.4 mm).
  A bare number is already mm.
- height is floor to top, width is side to side, depth is front to back.
- almirah / almari / cupboard = wardrobe. Doors / palla / shutter = shutters.
  khana / rack / shelf = shelves. Daraz = drawers.
- Never guess a size that is not in the text.
"""


def extract_furniture_params(description: str) -> dict[str, Any]:
    """Pull overall size and counts out of free text in any language.

    The caller (`furniture.parse_spec`) validates every value and does all
    panel arithmetic itself.
    """
    content = _complete(
        [
            {"role": "system", "content": _PARAMS_SYSTEM},
            {"role": "user", "content": description[:2000]},
        ],
        json_mode=True,
        max_tokens=1024,
        temperature=0.0,
    )
    return _loads(content)


_SKETCH_SYSTEM = f"""\
You are shown a photo of a hand-drawn sketch, a printed drawing or a
screenshot of ONE piece of cabinet furniture, with sizes written on it.
Read the overall parameters. Do NOT calculate any panel sizes.

Respond ONLY with a JSON object. Use these keys, omitting every key you cannot
read with confidence:

{_PARAM_KEYS}

Also include "readable": true or false. Use false when the picture is not a
furniture drawing or the sizes cannot be read.

Rules:
- Convert feet, inches and cm to mm (1 ft = 304.8 mm, 1 in = 25.4 mm). A bare
  number on a drawing in India is usually mm when above 100, otherwise feet or
  inches as marked.
- Count shelves, shutters and drawers only if they are drawn or written.
- Never guess a size that is not written in the picture.
"""


def read_sketch(image: bytes, mime_type: str) -> dict[str, Any]:
    """Read furniture parameters from a photo of a sketch. Values are unvalidated."""
    if mime_type not in IMAGE_TYPES:
        raise ValueError("Use a JPG, PNG or WebP photo.")
    if not image:
        raise ValueError("The photo is empty.")
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError(f"The photo is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
    encoded = base64.b64encode(image).decode("ascii")
    content = _complete(
        [
            {"role": "system", "content": _SKETCH_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read this furniture drawing. Answer with JSON only."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                ],
            },
        ],
        model=vision_model(),
        json_mode=True,
        max_tokens=1024,
        temperature=0.0,
    )
    return _loads(content)


# ---------------------------------------------------------------------------
# 2. Speech -> text
# ---------------------------------------------------------------------------

_SPEECH_HINT = (
    "A carpenter describing furniture: wardrobe, almirah, loft, kitchen base unit, "
    "shutter, shelf, drawer, plywood, 2100 mm high, 7 feet, 18 mm."
)


def transcribe(audio: bytes, filename: str = "speech.webm", language: str | None = None) -> str:
    """Turn a short voice note into text. The language is detected unless given."""
    if not audio:
        raise ValueError("The recording is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("The recording is too long. Keep it under a minute.")
    kwargs: dict[str, Any] = {
        "file": (filename, audio),
        "model": speech_model(),
        "prompt": _SPEECH_HINT,
        "response_format": "json",
        "temperature": 0.0,
    }
    if language:
        kwargs["language"] = language
    client = _client()
    try:
        result = client.audio.transcriptions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.error("AI transcription failed: %s", exc)
        raise AIError("We could not hear that recording. Try again, closer to the microphone.") from exc
    return (getattr(result, "text", "") or "").strip()


# ---------------------------------------------------------------------------
# 3. Part naming
# ---------------------------------------------------------------------------

_LABEL_SYSTEM = """\
You are an Indian furniture and modular cabinetry expert. Given a list of boards extracted from a 3D model,
assign each board a clear, human-readable label that a carpenter would recognise on an Indian shop floor.

Rules:
- Use common woodworking terms (Side, Top, Bottom, Shelf, Back, Shutter, Partition, Skirting, Drawer Front).
- If source_objects hint at the component name, use that context.
- If multiple boards share identical dimensions, differentiate them (Left Side, Right Side, Shelf 1, Shelf 2).
- Keep labels SHORT (2-4 words max).
- Respond with a JSON object: {"labels": {"board_id": "Human Label", ...}}
- Do NOT add any explanation, only the JSON object.
"""


def label_parts(boards: list[dict[str, Any]]) -> dict[str, str]:
    """Suggest a name for each board. Returns board_id -> label."""
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
            entry["source_objects"] = src[:3]
        compact.append(entry)

    content = _complete(
        [
            {"role": "system", "content": _LABEL_SYSTEM},
            {"role": "user", "content": json.dumps(compact, indent=None)},
        ],
        json_mode=True,
        max_tokens=4096,
    )
    labels = _loads(content).get("labels", {})
    known = {b["id"] for b in boards}
    return {str(k): str(v).strip()[:80] for k, v in labels.items() if k in known and str(v).strip()}


# ---------------------------------------------------------------------------
# 4. Plan assistant: answers questions and proposes changes
# ---------------------------------------------------------------------------

_ASSISTANT_SYSTEM = """\
You are the assistant inside CutList, a cutting-plan tool used by furniture
workshops in India. You are given FACTS about one cutting plan. The facts were
computed by the software and are correct.

Respond ONLY with a JSON object:
{"reply": "<your answer, short, plain markdown>", "actions": [ ... ]}

How to answer
- Use only numbers that appear in FACTS. Never work out sheet counts, tape
  lengths, costs or totals yourself. If a number is not in FACTS, say the plan
  must be re-run to know it.
- Be brief and practical. The reader is a carpenter on a shop floor.
- Reply in: {language}.
- If asked for a message for the customer, write it ready to paste into
  WhatsApp, using the saved quote total from FACTS if there is one. Never
  reveal the workshop's costs or margin in a customer message.

Proposing changes ("actions")
Every row in FACTS reads "row. id=part_NNN: ...". The row number is only the
position in the list, sorted by size. The id is the part's real name in the
plan, and it is what the user sees in the parts list and downloads.
If the user refers to a part by its id (for example part_011), find the FACTS
row with that exact id and pass it as part_id (or part_ids) in the action.
Never treat a part id as a row number: part_011 is usually not row 11.
Use row numbers only when the user refers to a position or to parts by name.
Add an action only when the user asks for a change. You cannot apply anything:
the user sees each proposal with an Apply button. Say in "reply" what you are
proposing. Allowed actions:

1. Edge banding (tape on part edges):
   {"type": "edge_band", "rows": "all" or [row numbers] or "part_ids": ["part_NNN", ...],
    "edges": "front" | "long" | "all" | "none", "tape_mm": 0.5 to 2}
   "front" = one long edge, "long" = both long edges, "all" = all four,
   "none" = remove the tape. If the user gives no thickness use 2 for
   shutters and drawer fronts and 0.5 for other parts, and say so.
2. Rename a part:
   {"type": "rename", "part_id": "part_NNN" (or "row": <row number>), "name": "<2 to 4 words>"}
   When asked to name parts, name only rows whose name is generic
   (Part 1, Object, Mesh, Group) using their size and thickness.
3. Customer quote. Include only the fields the user gave:
   {"type": "quote", "labour": <amount>, "hardware": <amount>,
    "other": <amount>, "tape_rate": <price per metre>,
    "margin_percent": <0 to 500>, "customer": "<name>", "note": "<text>"}

Anything else (changing a part's size, adding or removing parts, changing the
sheet size) cannot be done from here. Say so and say where it is done: sizes
are changed in the design or the description, then the plan is made again.
If no change is asked for, "actions" is [].
"""


def assistant(
    message: str,
    facts: str,
    history: list[dict[str, str]] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Answer a question about a plan. Returns {"reply": str, "actions": [raw dicts]}.

    The actions are unvalidated model output; pass them through
    `assistant.resolve_actions` before showing them to anyone.
    """
    system = _ASSISTANT_SYSTEM.replace("{language}", LANGUAGES.get(language, LANGUAGES["en"]))
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "system", "content": f"FACTS\n{facts}"},
    ]
    for turn in (history or [])[-10:]:
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": turn["role"], "content": turn["content"][:4000]})
    messages.append({"role": "user", "content": message[:4000]})

    content = _complete(messages, json_mode=True, max_tokens=4096, temperature=0.3)
    parsed = _loads(content)
    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        # The model ignored the JSON contract: show what it wrote, propose nothing.
        return {"reply": content.strip() or "I could not answer that. Please ask again.", "actions": []}
    actions = parsed.get("actions")
    return {
        "reply": reply.strip(),
        "actions": [a for a in actions if isinstance(a, dict)][:20] if isinstance(actions, list) else [],
    }


def chat(
    message: str,
    context: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Plain question answering about a plan (no proposals). Used by the single-user app."""
    from .assistant import plan_facts

    facts = plan_facts(context) if context else "No plan is loaded."
    return assistant(message, facts, history)["reply"]


# ---------------------------------------------------------------------------
# 5. Tips shown on a finished plan
# ---------------------------------------------------------------------------

_SUGGEST_SYSTEM = """\
You are an experienced modular furniture maker in India. You are given FACTS
about one cutting plan, computed by software and correct.

Write 3 to 5 short bullet points of practical advice for this job: saving
material, edge banding, hardware, assembly order, moisture-resistant board for
kitchens and bathrooms. Use only numbers that appear in FACTS and never work
out new totals. No introduction and no closing line.
"""


_EXPLAIN_SYSTEM = """\
You help a furniture workshop in India whose cutting plan was made from a 3D
model that has problems. FACTS lists the problems the software found by
measuring the model. They are correct.

Respond ONLY with a JSON object:
{"headline": "<one sentence: what is wrong overall>",
 "explanation": "<2 to 4 short sentences in plain words: what this means for
  the plan and the money, and what is probably going on in the model>",
 "steps": ["<a concrete thing to do in the 3D program, 2 to 4 of these>"]}

Rules
- Use only numbers that appear in FACTS. Never work out totals, percentages or
  costs. If a number is not in FACTS, leave it out.
- Say only what FACTS supports. Do not guess at causes FACTS does not hint at;
  write "probably" when you infer.
- The File line tells you the file type. If it is a SketchUp file or the
  steps would differ by program, name the program only when you are sure.
- Plain words, no jargon. The reader is a carpenter or a designer, not an
  engineer.
"""


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def explain_model_problems(facts: str) -> dict[str, Any] | None:
    """The model's problems explained in plain words, or None.

    None when AI is off, the call fails, the answer is malformed, or the answer
    uses a number that is not in `facts`. The caller then shows the
    software's own wording, which says the same thing.
    """
    if not llm_available() or not facts.strip():
        return None
    try:
        content = _complete(
            [
                {"role": "system", "content": _EXPLAIN_SYSTEM},
                {"role": "user", "content": f"FACTS\n{facts}"},
            ],
            json_mode=True,
            max_tokens=2048,
            temperature=0.3,
        )
        data = _loads(content)
    except (AIError, ValueError):
        return None
    headline = str(data.get("headline") or "").strip()
    explanation = str(data.get("explanation") or "").strip()
    steps = [str(s).strip() for s in (data.get("steps") or []) if str(s).strip()][:4]
    if not headline or not explanation:
        return None
    allowed = set(_NUMBER.findall(facts))
    said = set(_NUMBER.findall(" ".join([headline, explanation, *steps])))
    invented = said - allowed
    if invented:
        logger.warning("AI model-problem answer used numbers not in the facts: %s", sorted(invented))
        return None
    return {"headline": headline[:240], "explanation": explanation[:900], "steps": [s[:240] for s in steps]}


def suggest_improvements(context: dict[str, Any]) -> str | None:
    """Short tips for a finished plan, or None when AI is off or fails."""
    if not llm_available():
        return None
    from .assistant import plan_facts

    try:
        content = _complete(
            [
                {"role": "system", "content": _SUGGEST_SYSTEM},
                {"role": "user", "content": f"FACTS\n{plan_facts(context)}"},
            ],
            max_tokens=2048,
            temperature=0.4,
        )
    except AIError:
        return None
    return content.strip() or None
