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
