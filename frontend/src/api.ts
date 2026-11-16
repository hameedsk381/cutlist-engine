import axios from 'axios';
import type { ExtractResult, FinalizeResult, ProcessResult, ReviewDecisions } from './types';

const api = axios.create({ baseURL: '' });

export async function healthCheck() {
  const r = await api.get('/healthz');
  return r.data;
}

export async function processOneShot(file: File, config: Record<string, number>): Promise<ProcessResult> {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(config).forEach(([k, v]) => fd.append(k, String(v)));
  const r = await api.post('/api/process', fd);
  return r.data;
}

export async function extractBoards(file: File, config: Record<string, unknown>): Promise<ExtractResult> {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(config).forEach(([k, v]) => fd.append(k, String(v)));
  const r = await api.post('/api/extract', fd);
  return r.data;
}

export async function finalizeSession(
  sessionId: string,
  review: ReviewDecisions,
  overrides: Record<string, unknown> = {},
  force = false,
): Promise<FinalizeResult> {
  const r = await api.post(`/api/finalize/${sessionId}`, {
    review,
    overrides,
    emit_gcode: true,
    force,
  });
  return r.data;
}

export async function aiDescribe(description: string, config: Record<string, number>): Promise<ProcessResult> {
  const r = await api.post('/api/ai/describe', { description, ...config });
  return r.data;
}

export async function aiChat(
  message: string,
  context?: unknown,
  history?: { role: string; content: string }[],
  sessionId?: string,
): Promise<string> {
  const r = await api.post('/api/ai/chat', { message, context, history, session_id: sessionId || '' });
  return r.data.response;
}

export function downloadUrl(sessionId: string, filename: string): string {
  return `/api/download/${sessionId}/${filename}`;
}

/** Turn any request failure into a sentence a workshop user can act on. */
export function friendlyError(error: unknown, fallback: string): string {
  const err = error as { code?: string; response?: { status?: number; data?: { detail?: unknown } } };
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (err?.code === 'ERR_NETWORK' || (err?.response?.status ?? 0) >= 502) {
    return 'Cannot reach the CutList server. Check that it is running, then try again.';
  }
  if (err?.response?.status === 413) return 'That file is too large to upload.';
  return fallback;
}
