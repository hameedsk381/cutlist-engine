import axios from 'axios';
import type { ExtractResult, FinalizeResult, ProcessResult, ReviewDecisions } from './types';

/**
 * Bearer token for /api/* routes.
 * - Build time: VITE_API_TOKEN is embedded into the bundle (Docker build arg).
 * - Runtime:    localStorage 'cutlist_api_token' overrides the build-time value,
 *               e.g. localStorage.setItem('cutlist_api_token', '...')
 */
export const apiToken: string =
  (typeof window !== 'undefined' && window.localStorage.getItem('cutlist_api_token')) ||
  (import.meta.env.VITE_API_TOKEN as string | undefined) ||
  '';

/**
 * Desktop (Tauri) apps talk to the bundled Python engine sidecar on
 * 127.0.0.1:8765; the browser app uses same-origin (empty baseURL).
 */
const DESKTOP_API_BASE =
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
    ? 'http://127.0.0.1:8765'
    : '';

const api = axios.create({ baseURL: DESKTOP_API_BASE });

if (apiToken) {
  api.interceptors.request.use((config) => {
    config.headers.set('Authorization', `Bearer ${apiToken}`);
    return config;
  });
}

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

/**
 * Download or open a protected artifact with the Authorization header attached.
 * Plain <a href> navigation cannot carry headers, so we fetch the file as a
 * blob and hand it to the browser.
 */
export async function saveArtifact(url: string, filename: string, openInNewTab = false): Promise<void> {
  const r = await api.get(url, { responseType: 'blob' });
  const blobUrl = URL.createObjectURL(r.data as Blob);
  if (openInNewTab) {
    window.open(blobUrl, '_blank');
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  } else {
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(blobUrl);
  }
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
