import type { AssistantAnswer, BrandProfile, LinearPlan, PartOverrides, QuoteInput } from './types';
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

export interface DescribedModel {
  filename: string;
  title: string;
  obj: string;
  notes: string[];
  parts: { name: string; length: number; width: number; thickness: number }[];
}

/** Description -> a real 3D model file. Sizes are computed on the server from carcass rules. */
export async function describeToModel(description: string, thickness: number): Promise<DescribedModel> {
  const r = await api.post('/api/describe', { description, thickness });
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

export async function requestPasswordReset(email: string): Promise<void> {
  await api.post('/auth/forgot', _form({ email }));
}

export async function resetPassword(token: string, password: string): Promise<SaaSUser> {
  const r = await api.post('/auth/reset', _form({ token, password }));
  setSaasToken(r.data.token);
  return r.data.user as SaaSUser;
}

export async function deleteProject(id: number): Promise<void> {
  await api.delete(`/api/projects/${id}`);
}

export async function deleteAccount(password: string): Promise<void> {
  await api.delete('/auth/me', { data: _form({ password }) });
  clearSaasToken();
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

export async function createProjectFromDescription(
  description: string, config: Record<string, unknown>, useOffcuts = false,
): Promise<{ project: SaaSProject; notes: string[] }> {
  const fd = new FormData();
  fd.append('description', description);
  Object.entries(config).forEach(([k, v]) => fd.append(k, String(v)));
  if (useOffcuts) fd.append('use_offcuts', 'true');
  const r = await api.post('/api/projects/describe', fd);
  return { project: r.data.project as SaaSProject, notes: (r.data.notes || []) as string[] };
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

export async function updateProjectSettings(
  id: number, body: { overrides?: PartOverrides; quote?: QuoteInput | null },
): Promise<{ project: SaaSProjectDetail; rerun: boolean; job_id: number | null }> {
  const r = await api.put(`/api/projects/${id}/settings`, body);
  return r.data;
}

export async function getBrand(): Promise<BrandProfile> {
  return (await api.get('/api/brand')).data;
}

export async function saveBrand(brand: Partial<BrandProfile>): Promise<BrandProfile> {
  return (await api.put('/api/brand', brand)).data;
}

export async function uploadLogo(file: File): Promise<BrandProfile> {
  const fd = new FormData();
  fd.append('file', file);
  return (await api.post('/api/brand/logo', fd)).data;
}

export async function deleteLogo(): Promise<BrandProfile> {
  return (await api.delete('/api/brand/logo')).data;
}

/** The saved logo as a temporary address for an <img>, or null when there is none. */
export async function logoPreviewUrl(): Promise<string | null> {
  try {
    const r = await api.get('/api/brand/logo', { responseType: 'blob' });
    return URL.createObjectURL(r.data as Blob);
  } catch {
    return null;
  }
}

/** Download the client's quote as a PDF. The server explains why in plain words when it cannot make it. */
export async function downloadQuotePdf(projectId: number, name: string, withParts: boolean): Promise<void> {
  try {
    const r = await api.get(`/api/projects/${projectId}/quote.pdf`, { params: { parts: withParts }, responseType: 'blob' });
    const blobUrl = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `${name.replace(/[^A-Za-z0-9._-]+/g, '-') || 'quote'}-quote.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
  } catch (err) {
    // A failed PDF request comes back as a blob; read the sentence out of it.
    const data = (err as { response?: { data?: unknown } })?.response?.data;
    if (data instanceof Blob) {
      try {
        const detail = JSON.parse(await data.text())?.detail;
        if (typeof detail === 'string') throw new Error(detail, { cause: err });
      } catch (inner) {
        if (inner instanceof Error && inner.message) throw inner;
      }
    }
    throw err;
  }
}

export async function linearNest(payload: Record<string, unknown>): Promise<LinearPlan> {
  const r = await api.post('/api/tools/linear', payload);
  return r.data;
}

// ---------------------------------------------------------------------------
// AI: voice, sketch photo and the plan assistant (signed-in users)
// ---------------------------------------------------------------------------

/** Whether the server has AI switched on. Never throws: no AI just hides the controls. */
export async function aiAvailable(): Promise<boolean> {
  try {
    const r = await api.get('/api/tools/ai');
    return !!r.data.available;
  } catch {
    return false;
  }
}

export async function transcribeSpeech(audio: Blob): Promise<string> {
  const fd = new FormData();
  const ext = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm';
  fd.append('file', audio, `speech.${ext}`);
  const r = await api.post('/api/tools/ai/transcribe', fd);
  return r.data.text as string;
}

export async function readSketch(photo: File): Promise<{ description: string; missing: string[] }> {
  const fd = new FormData();
  fd.append('file', photo);
  const r = await api.post('/api/tools/ai/sketch', fd);
  return r.data;
}

export async function askAssistant(
  projectId: number, message: string, history: { role: string; content: string }[], language: string,
): Promise<AssistantAnswer> {
  const r = await api.post(`/api/projects/${projectId}/ai/chat`, { message, history, language });
  return r.data as AssistantAnswer;
}
