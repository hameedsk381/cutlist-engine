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

export async function extractBoards(file: File, config: Record<string, any>): Promise<ExtractResult> {
  const fd = new FormData();
  fd.append('file', file);
  Object.entries(config).forEach(([k, v]) => fd.append(k, String(v)));
  const r = await api.post('/api/extract', fd);
  return r.data;
}

export async function finalizeSession(
  sessionId: string,
  review: ReviewDecisions,
  overrides: Record<string, any> = {},
): Promise<FinalizeResult> {
  const r = await api.post(`/api/finalize/${sessionId}`, {
    review,
    overrides,
    emit_gcode: true,
    force: false,
  });
  return r.data;
}

export async function aiDescribe(description: string, config: Record<string, number>): Promise<ProcessResult> {
  const r = await api.post('/api/ai/describe', { description, ...config });
  return r.data;
}

export async function aiChat(
  message: string,
  context?: any,
  history?: { role: string; content: string }[],
  sessionId?: string,
): Promise<string> {
  const r = await api.post('/api/ai/chat', { message, context, history, session_id: sessionId || '' });
  return r.data.response;
}

export function downloadUrl(sessionId: string, filename: string): string {
  return `/api/download/${sessionId}/${filename}`;
}
