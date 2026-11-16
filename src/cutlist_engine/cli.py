from __future__ import annotations

import argparse
from pathlib import Path

from .dxf_export import write_sheets_dxf_zip
from .gcode_export import GCodeConfig, write_sheets_gcode
from .outputs import (
    write_cutlist_csv,
    write_json_report,
    write_label_sheet_html,
    write_sheet_layout_html,
)
from .parsers import load_model
from .pipeline import (
    ProcessConfig,
    load_materials,
    load_overrides,
    load_review,
    process_triangles,
)


def _parse_sheet_sizes(spec: str | None) -> tuple[tuple[str, float, float, float], ...]:
    if not spec:
        return ()
    out = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        cost = 0.0
        if "@" in chunk:
            size_part, cost_part = chunk.split("@", 1)
            cost = float(cost_part)
        else:
            size_part = chunk
        w_str, h_str = size_part.lower().split("x")
        w, h = float(w_str), float(h_str)
        out.append((f"{int(round(w))}x{int(round(h))}", w, h, cost))
    return tuple(out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract plywood cutlists, optimize sheet usage, and emit CNC-ready cutting plans.",
    )
    parser.add_argument("input", type=Path, help="Input .json, .dxf, .obj, .stl, or .dae file")
    parser.add_argument("--output-dir", type=Path, default=Path("out"))

    # Material defaults
    parser.add_argument("--sheet-width", type=float, default=2440.0)
    parser.add_argument("--sheet-height", type=float, default=1220.0)
    parser.add_argument("--thickness", type=float, default=18.0)
    parser.add_argument("--thickness-tolerance", type=float, default=0.5)
    parser.add_argument("--kerf", type=float, default=3.0, help="Saw blade kerf width in mm.")
    parser.add_argument("--sheet-cost", type=float, default=55.0)
    parser.add_argument("--currency", type=str, default="USD")

    # Offcut + nesting
    parser.add_argument("--min-reusable-offcut-width", type=float, default=300.0)
    parser.add_argument("--min-reusable-offcut-height", type=float, default=300.0)
    parser.add_argument("--candidate-sheet-sizes", type=str, default=None,
                        help="Alt sheet sizes with optional cost: '2440x1220@55,3050x1525@90'.")

    # Quality + filters
    parser.add_argument("--grain-locked", action="store_true",
                        help="Treat all panels as grain-locked: no 90 deg rotation in nesting.")
    parser.add_argument("--min-part-length", type=float, default=50.0,
                        help="Drop boards below this long-edge length (mm). Removes mesh slivers.")
    parser.add_argument("--min-part-width", type=float, default=50.0)
    parser.add_argument("--min-confidence", type=float, default=0.6,
                        help="Gate cutlist below this extraction confidence.")
    parser.add_argument("--force", action="store_true",
                        help="Emit cutlist even when below --min-confidence.")

    # Side-car JSON files
    parser.add_argument("--overrides", type=Path, default=None,
                        help="JSON file of per-part overrides keyed by board id or source object name.")
    parser.add_argument("--materials", type=Path, default=None,
                        help="JSON file mapping material name -> {thickness, sheet_width, sheet_height, sheet_cost}.")
    parser.add_argument("--review", type=Path, default=None,
                        help="JSON file of operator review decisions (accept/reject/rename) keyed by board id.")

    # Output toggles
    parser.add_argument("--no-dxf", action="store_true", help="Skip per-sheet DXF emission.")
    parser.add_argument("--no-labels", action="store_true", help="Skip printable label sheet emission.")
    parser.add_argument("--gcode", action="store_true", help="Emit RS-274 G-code per sheet (CNC routers / plasma).")
    parser.add_argument("--feed-rate", type=float, default=2500.0, help="G-code lateral feed rate (mm/min).")
    parser.add_argument("--plunge-rate", type=float, default=800.0, help="G-code Z plunge feed rate (mm/min).")
    parser.add_argument("--spindle-rpm", type=int, default=18000, help="G-code spindle RPM (set 0 for laser/plasma/saw).")
    parser.add_argument("--cut-depth", type=float, default=18.5, help="G-code total Z depth below stock surface (mm).")
    parser.add_argument("--pass-depth", type=float, default=6.0, help="G-code max Z step per pass (mm).")
    parser.add_argument("--safe-z", type=float, default=15.0, help="G-code safe-travel Z above stock (mm).")
    parser.add_argument("--clearance-z", type=float, default=2.0, help="G-code Z to drop to before plunge feed (mm).")
    parser.add_argument("--gcode-units", choices=["mm", "in"], default="mm", help="G-code units (G21 / G20).")

    args = parser.parse_args()

    overrides = load_overrides(args.overrides) if args.overrides else {}
    materials = load_materials(args.materials) if args.materials else {}
    review = load_review(args.review) if args.review else {}

    triangles = load_model(args.input)
    result = process_triangles(
        triangles,
        ProcessConfig(
            sheet_width=args.sheet_width,
            sheet_height=args.sheet_height,
            material_thickness=args.thickness,
            thickness_tolerance=args.thickness_tolerance,
            kerf=args.kerf,
            min_reusable_offcut_width=args.min_reusable_offcut_width,
            min_reusable_offcut_height=args.min_reusable_offcut_height,
            grain_locked=args.grain_locked,
            min_part_length=args.min_part_length,
            min_part_width=args.min_part_width,
            min_confidence=args.min_confidence,
            sheet_cost=args.sheet_cost,
            currency=args.currency,
            candidate_sheet_sizes=_parse_sheet_sizes(args.candidate_sheet_sizes),
            overrides=overrides,
            materials=materials,
            review=review,
        ),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json_report(
        args.output_dir / "report.json",
        result.boards,
        result.cutlist,
        result.sheets,
        result.extraction_report,
        result.material_summary,
        result.waste_optimization_report,
        result.model_fix_report,
        result.sheet_size_options,
        kerf=result.kerf,
    )

    fix = result.model_fix_report
    gate_failed = fix is not None and not fix.passes_gate

    if gate_failed and not args.force:
        write_sheet_layout_html(
            args.output_dir / "sheet_layout.html",
            result.sheets,
            result.material_summary,
            result.boards,
            result.model_fix_report,
            result.sheet_size_options,
        )
        (args.output_dir / "cutlist.csv").write_text(
            "# cutlist gated: confidence below threshold. Re-run with --force to emit anyway.\n",
            encoding="utf-8",
        )
        print(f"GATED: confidence {fix.confidence:.1%} < min {fix.confidence_threshold:.0%}")
        for issue in fix.issues:
            print(f"  issue: {issue}")
        for rec in fix.recommendations:
            print(f"  fix:   {rec}")
        print(f"Diagnosis written to: {args.output_dir}")
        print("Re-run with --force to produce the cutlist anyway.")
        return

    write_cutlist_csv(args.output_dir / "cutlist.csv", result.cutlist)
    write_sheet_layout_html(
        args.output_dir / "sheet_layout.html",
        result.sheets,
        result.material_summary,
        result.boards,
        result.model_fix_report,
        result.sheet_size_options,
    )
    if not args.no_labels:
        write_label_sheet_html(args.output_dir / "labels.html", result.cutlist, result.sheets)
    if not args.no_dxf and result.sheets:
        dxf_paths = write_sheets_dxf_zip(args.output_dir / "dxf", result.sheets, result.boards, kerf=args.kerf)
        print(f"DXF sheets written: {len(dxf_paths)} -> {args.output_dir / 'dxf'}")
    if args.gcode and result.sheets:
        gcfg = GCodeConfig(
            feed_rate=args.feed_rate,
            plunge_rate=args.plunge_rate,
            spindle_rpm=args.spindle_rpm,
            cut_depth=args.cut_depth,
            pass_depth=args.pass_depth,
            safe_z=args.safe_z,
            clearance_z=args.clearance_z,
            units=args.gcode_units,
        )
        gcode_paths = write_sheets_gcode(args.output_dir / "gcode", result.sheets, result.boards,
                                          kerf=args.kerf, config=gcfg)
        print(f"G-code sheets written: {len(gcode_paths)} -> {args.output_dir / 'gcode'}")

    print(f"Detected boards: {len(result.boards)}  (rejected by review: {len(result.rejected_boards)})")
    print(f"Extraction confidence: {result.extraction_report.confidence:.1%}")
    print(f"Cutlist rows: {len(result.cutlist)}")
    print(f"Sheets required: {len(result.sheets)}")
    if result.per_material_summaries and len(result.per_material_summaries) > 1:
        print("Per-material breakdown:")
        for summary in result.per_material_summaries:
            print(
                f"  {summary.sheet_size_label:<32s}  sheets={summary.sheet_count:<3d} "
                f"util={summary.utilization_percent:5.1f}%  cost={summary.currency} {summary.total_material_cost:,.2f}"
            )
    print(f"Material utilization: {result.material_summary.utilization_percent:.1f}%")
    print(f"Reusable offcuts: {result.material_summary.reusable_offcut_area:.2f} sq m")
    if result.material_summary.total_material_cost > 0:
        print(
            f"Total material cost: {result.material_summary.currency} "
            f"{result.material_summary.total_material_cost:,.2f}"
        )
        if result.material_summary.cost_savings_vs_worst_strategy > 0:
            print(
                f"Savings vs worst strategy: {result.material_summary.currency} "
                f"{result.material_summary.cost_savings_vs_worst_strategy:,.2f}"
            )
    if result.sheet_size_options and len(result.sheet_size_options) > 1:
        print("Sheet size comparison (cheapest first):")
        for option in result.sheet_size_options:
            print(
                f"  {option.label:>12s}  sheets={option.sheet_count:<3d} "
                f"util={option.utilization_percent:5.1f}%  total={result.material_summary.currency} {option.total_cost:,.2f}"
            )
    print(f"Reports written to: {args.output_dir}")
    if result.waste_optimization_report:
        print(f"Selected nesting strategy: {result.waste_optimization_report.selected_strategy}")
    for sheet in result.sheets:
        tag = f" [{sheet.material}]" if sheet.material and sheet.material != "default" else ""
        print(f"Sheet {sheet.sheet_id}{tag}: waste {sheet.waste_percent:.1f}%")
    for warning in result.extraction_report.warnings:
        print(f"Warning: {warning}")
    if fix and not fix.passes_gate:
        print("NOTE: confidence below threshold but --force used; review model_fix_report.")


if __name__ == "__main__":
    main()
