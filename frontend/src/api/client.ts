export const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `Request failed (${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const post = <T = any>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });
export const put = <T = any>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) });
export function resourceUrl(path: string) { return /^https?:\/\//.test(path) ? path : `${BASE}${path}`; }

export type Form = Record<string, string | number | null>;
export type Scenario = { id: string; title: string; description: string; expected_decision: string; form: Form; documents: string[] };
export type RunRow = { run_id: string | number; vendor_name: string; country: string; decision?: string; status?: string; risk_score: number | null; duration_ms: number; created_at: string; parent_run_id?: number | null };
export type Stage = { stage_no: number; name: string; type: string; status: string; summary?: string; duration_ms?: number; findings?: any[]; data?: any; input_json?: any; output_json?: any; started_at?: string; rule_version?: string };
export type Run = { run_id: string | number; submission_id: string; status: string; decision?: string; risk_score: number | null; confidence?: number; risk_breakdown: any[]; reasons: any[]; what_would_change: any[]; form: Form; documents: { id: number; filename: string; doc_type_detected?: string; url: string }[]; stages: Stage[]; messages: { id: number; audience: string; subject: string; body: string; sent_at: string | null }[]; overrides: any[]; diff_from_parent: { resolved: any[]; still_open: any[]; new: any[] } | null; parent_run_id?: number | null };
