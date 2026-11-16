import axios from 'axios';
import type {
  ExtractResult, FinalizeResult, ProcessResult, ReviewDecisions,
  SaaSApiKey, SaaSApiKeyCreated, SaaSOffcutList, SaaSProject, SaaSProjectDetail, SaaSUser,
} from './types';

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

// ---------------------------------------------------------------------------
// SaaS session token (JWT from /auth/login) — takes priority over the legacy
// shared CUTLIST_API_TOKEN.
// ---------------------------------------------------------------------------
const SAAS_TOKEN_KEY = 'cutlist_saas_token';

export function getSaasToken(): string {
  try {
    return window.localStorage.getItem(SAAS_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setSaasToken(token: string): void {
  window.localStorage.setItem(SAAS_TOKEN_KEY, token);
}

export function clearSaasToken(): void {
  window.localStorage.removeItem(SAAS_TOKEN_KEY);
}

function bearer(): string | null {
  const saas = getSaasToken();
  if (saas) return `Bearer ${saas}`;
  return apiToken ? `Bearer ${apiToken}` : null;
}

api.interceptors.request.use((config) => {
  const auth = bearer();
  if (auth) config.headers.set('Authorization', auth);
  return config;
});

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

// ---------------------------------------------------------------------------
// SaaS: accounts, projects, jobs
// ---------------------------------------------------------------------------

function _form(data: Record<string, string>): FormData {
  const fd = new FormData();
  Object.entries(data).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

export async function saasSignup(email: string, password: string): Promise<SaaSUser> {
  const r = await api.post('/auth/signup', _form({ email, password }));
  setSaasToken(r.data.token);
  return r.data.user as SaaSUser;
}

export async function saasLogin(email: string, password: string): Promise<SaaSUser> {
  const r = await api.post('/auth/login', _form({ email, password }));
  setSaasToken(r.data.token);
  return r.data.user as SaaSUser;
}

export async function saasMe(): Promise<SaaSUser> {
  const r = await api.get('/auth/me');
  return r.data as SaaSUser;
}

export async function createProject(
  file: File, name: string, config: Record<string, unknown>, useOffcuts = false,
): Promise<SaaSProject> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('name', name);
  Object.entries(config).forEach(([k, v]) => fd.append(k, String(v)));
  if (useOffcuts) fd.append('use_offcuts', 'true');
  const r = await api.post('/api/projects', fd);
  return r.data.project as SaaSProject;
}

export async function listProjects(): Promise<SaaSProject[]> {
  const r = await api.get('/api/projects');
  return r.data as SaaSProject[];
}

export async function getProject(id: number): Promise<SaaSProjectDetail> {
  const r = await api.get(`/api/projects/${id}`);
  return r.data as SaaSProjectDetail;
}

export async function rerunProject(id: number): Promise<void> {
  await api.post(`/api/projects/${id}/jobs`);
}

export function artifactDownloadUrl(projectId: number, path: string): string {
  return `${DESKTOP_API_BASE}/api/projects/${projectId}/download/${path}`;
}

// ---------------------------------------------------------------------------
// SaaS M3: email verification, API keys, share links
// ---------------------------------------------------------------------------

export async function resendVerification(): Promise<{ verified: boolean; sent?: boolean }> {
  const r = await api.post('/auth/resend-verification');
  return r.data;
}

export async function listApiKeys(): Promise<SaaSApiKey[]> {
  const r = await api.get('/auth/api-keys');
  return r.data as SaaSApiKey[];
}

export async function createApiKey(name: string): Promise<SaaSApiKeyCreated> {
  const r = await api.post('/auth/api-keys', _form({ name }));
  return r.data as SaaSApiKeyCreated;
}

export async function revokeApiKey(id: number): Promise<void> {
  await api.delete(`/auth/api-keys/${id}`);
}

export async function shareProject(id: number): Promise<{ share_url: string; has_result: boolean }> {
  const r = await api.post(`/api/projects/${id}/share`);
  return r.data;
}

export async function unshareProject(id: number): Promise<void> {
  await api.delete(`/api/projects/${id}/share`);
}

// ---------------------------------------------------------------------------
// SaaS M4: offcut shelf
// ---------------------------------------------------------------------------

export async function listOffcuts(): Promise<SaaSOffcutList> {
  const r = await api.get('/api/offcuts');
  return r.data as SaaSOffcutList;
}

export async function deleteOffcut(id: number): Promise<void> {
  await api.delete(`/api/offcuts/${id}`);
}

export async function saveProjectOffcuts(id: number): Promise<number> {
  const r = await api.post(`/api/projects/${id}/offcuts`);
  return r.data.saved as number;
}
