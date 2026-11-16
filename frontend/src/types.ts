export interface Board {
  id: string;
  label: string;
  length: number;
  width: number;
  thickness: number;
  area: number;
  material: string;
  priority: string;
  grain_locked: boolean;
  edge_band: number[];
  confidence: number;
  source_objects: string[];
  warnings: string[];
  contour: [number, number][];
  holes: [number, number][][];
  is_rectangular?: boolean;
}

export interface SheetPart {
  board_id: string;
  x: number;
  y: number;
  length: number;
  width: number;
  rotation: number;
  contour?: [number, number][];
  holes?: [number, number][][];
  priority?: string;
  label?: string;
}

export interface Offcut {
  x: number;
  y: number;
  width: number;
  height: number;
  area: number;
  reusable: boolean;
}

export interface Sheet {
  sheet_id: number;
  width: number;
  height: number;
  material: string;
  sheet_cost: number;
  currency: string;
  used_area: number;
  waste_percent: number;
  utilization_percent: number;
  parts: SheetPart[];
  offcuts: Offcut[];
  is_offcut_stock?: boolean;
  /** Saw cuts in order. Missing on projects planned before cut sequences existed. */
  cuts?: { ok: boolean; steps: CutStep[] };
}

export interface CutStep {
  step: number;
  /** 0 = cuts across the whole sheet, 1 = cuts on the strips they make, and so on. */
  stage: number;
  kind: 'split' | 'trim';
  /** horizontal: the cut line runs left-right on the drawing; vertical: top-bottom. */
  direction: 'horizontal' | 'vertical';
  /** mm from the sheet's top edge (horizontal) or left edge (vertical). */
  position: number;
  /** The same distance measured from the edge of the piece being cut. */
  from_edge: number;
  piece: [number, number];
  /** [x0, y0, x1, y1] of the cut line on the sheet. */
  line: [number, number, number, number];
  kerf: number;
  /** Parts that are finished once this cut is made. */
  frees: string[];
}

export interface MaterialSummary {
  sheet_count: number;
  waste_percent: number;
  utilization_percent: number;
  reusable_offcut_area: number;
  total_material_cost: number;
  currency: string;
}

export interface CutlistItem {
  id: string;
  length: number;
  width: number;
  thickness: number;
  quantity: number;
  material: string;
  labels?: string[];
  board_ids?: string[];
  finished_length?: number;
  finished_width?: number;
}

export interface ExtractionReport {
  triangle_count: number;
  usable_triangle_count: number;
  plane_count: number;
  surface_count: number;
  board_count: number;
  unmatched_surface_count: number;
  confidence: number;
  warnings: string[];
  solid_part_count?: number;
  inferred_board_count?: number;
  skipped_parts?: string[];
}

export interface ModelFixReport {
  confidence: number;
  confidence_threshold: number;
  passes_gate: boolean;
  issues: string[];
  recommendations: string[];
}

export interface ExtractResult {
  session_id: string;
  extraction_report: ExtractionReport;
  model_fix_report: ModelFixReport | null;
  boards: Board[];
}

export interface FinalizeResult {
  gated: boolean;
  artifacts: { name: string; url: string }[];
  summary: ProcessResult;
}

export interface ProcessResult {
  boards: Board[];
  cutlist: CutlistItem[];
  sheets: Sheet[];
  ai_advice: string | null;
  material_summary: MaterialSummary;
  extraction_report?: ExtractionReport;
  waste_optimization_report?: unknown;
  model_fix_report?: ModelFixReport | null;
  sheet_size_options?: unknown[];
  rejected_boards?: string[];
  edge_banding?: EdgeBandingSummary;
}

export interface ReviewDecisions {
  [boardId: string]: {
    accepted: boolean;
    rename: string;
    reason: string;
  };
}

export interface ProcessConfig {
  sheet_width: number;
  sheet_height: number;
  thickness: number;
  kerf: number;
  sheet_cost: number;
  currency: string;
}

export type AppView = 'upload' | 'review' | 'dashboard';

// ---------------------------------------------------------------------------
// SaaS (accounts + projects + async jobs)
// ---------------------------------------------------------------------------

export interface SaaSUser {
  id: number;
  email: string;
  plan: string;
  email_verified: boolean;
}

export interface SaaSJob {
  id: number;
  status: 'queued' | 'processing' | 'done' | 'failed';
  error: string | null;
  gated: boolean;
  artifacts: { name: string; path: string }[] | null;
  created_at: string | null;
  finished_at: string | null;
}

export interface SaaSProject {
  id: number;
  name: string;
  original_filename: string;
  created_at: string | null;
  job: SaaSJob | null;
}

export interface SaaSProjectDetail extends SaaSProject {
  result?: ProcessResult;
  settings?: { overrides: PartOverrides; quote: QuoteInput | null };
  quote_totals?: QuoteTotals | null;
}

export interface EdgeBandingSummary {
  total_m: number;
  by_thickness: { thickness: number; metres: number }[];
  banded_parts: number;
}

/** Per-part settings keyed by board id. edge_band is [top, right, bottom, left] in mm. */
export type PartOverrides = Record<string, { edge_band?: number[]; grain_locked?: boolean; label?: string }>;

export interface QuoteInput {
  labour: number;
  hardware: number;
  other: number;
  edge_band_rate: number;
  margin_percent: number;
  customer: string;
  note: string;
}

export interface QuoteTotals {
  currency: string;
  material: number;
  edge_banding: number;
  edge_banding_m: number;
  labour: number;
  hardware: number;
  other: number;
  subtotal: number;
  margin: number;
  total: number;
  customer: string;
  note: string;
}

export interface LinearPlan {
  bars: { bar_id: number; stock_length: number; is_leftover: boolean; cuts: { label: string; length: number }[]; remaining: number }[];
  new_bar_count: number;
  leftover_bar_count: number;
  total_piece_length: number;
  total_stock_length: number;
  waste_percent: number;
  total_cost: number;
  reusable_leftovers: number[];
}

export interface SaaSApiKey {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string | null;
  last_used_at: string | null;
}

export interface SaaSApiKeyCreated extends SaaSApiKey {
  key: string; // raw key, shown exactly once
}

export interface SaaSOffcut {
  id: number;
  length: number;
  width: number;
  thickness: number;
  material: string;
  area_m2: number;
  status: 'available' | 'reserved' | 'used';
  created_at: string | null;
}

export interface SaaSOffcutList {
  offcuts: SaaSOffcut[];
  count: number;
  total_area_m2: number;
}

/** A change the assistant suggests. It is saved only when the user presses Apply. */
export type AssistantProposal =
  | { type: 'overrides'; title: string; overrides: PartOverrides }
  | { type: 'quote'; title: string; quote: QuoteInput };

export interface AssistantAnswer {
  reply: string;
  proposals: AssistantProposal[];
}
