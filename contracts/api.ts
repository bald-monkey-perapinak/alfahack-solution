/** Browser adapter: tokens remain in memory. Never send LLM/operator keys to the browser. */
export type Role = 'cfo' | 'ceo' | 'treasurer' | 'chief_accountant' | 'owner' | 'other_executive';
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface Organization { id: number; name: string; synthetic_u: string; industry: string | null; region: string | null }
export interface User { id: number; name: string; email: string; role: Role; org_id: number }
export interface Session { access_token: string; token_type: 'bearer'; expires_at: string; user?: User }
export interface AnalysisOptions { material_ids?: number[]; max_events?: number; max_depth?: number; decay?: number; min_score?: number }
export interface Job {
  id: string; status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string; finished_at: string | null; error_code: string | null;
  summary: { total?: number | null; processed?: number; created?: number; skipped?: number; failed?: number; retrying?: boolean; materials?: { material_id: number; status: 'pending' | 'running' | 'completed' | 'skipped' | 'failed'; error_code: string | null; retries?: number }[] }; insight_ids?: number[];
}
export interface FeedItem {
  id: number; title: string; relevance_score: number; confidence: number; created_at: string;
  primary_material_id: number; generation_mode: 'offline' | 'live'; is_demo: boolean; warnings: string[];
}
export interface Evidence {
  id: number; material_id: number; section: string; claim: string; quote: string;
  source_title: string; source_ref: string; published_at: string | null;
}
export interface Insight {
  id: number; title: string; facts: string; bank_view: string | null; interpretation: string;
  relevance_reason: string; confidence: number; relevance_score: number;
  risks: string[]; opportunities: string[];
  suggested_actions: { type: string; label: string; rationale: string; priority: number }[];
  evidence: Evidence[]; steps: { tool: string; at: string; result: unknown }[];
  payload: { generation_mode: 'offline' | 'live'; is_demo: boolean; warnings: string[]; [key: string]: unknown };
}
export interface Material {
  id: number; title: string; body?: string; summary: string | null; published_at: string | null;
  material_type: 'news' | 'bank_analytics'; source_ref: string; is_demo: boolean;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}

export class AnalyticsApi {
  private token: string | null = null;
  constructor(private base = 'http://localhost:8000') {}
  setToken(token: string | null) { this.token = token; }
  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body) headers.set('Content-Type', 'application/json');
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    const response = await fetch(`${this.base}${path}`, { ...init, headers, credentials: 'omit' });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(response.status, data.error?.code ?? 'request_failed');
    }
    return response.status === 204 ? undefined as T : response.json();
  }
  organizations(q = '', offset = 0) {
    return this.request<Page<Organization>>(`/api/v1/organizations?q=${encodeURIComponent(q)}&offset=${offset}`);
  }
  async register(body: { email: string; password: string; name: string; role: Role; organization_id: number }) {
    const session = await this.request<Session>('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(body) });
    this.setToken(session.access_token); return session;
  }
  async login(email: string, password: string) {
    const session = await this.request<Session>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    this.setToken(session.access_token); return session;
  }
  async logout() { await this.request<void>('/api/v1/auth/logout', { method: 'POST' }); this.setToken(null); }
  me() { return this.request<User>('/api/v1/me'); }
  updateMe(body: { name?: string; role?: Role; organization_id?: number }) {
    return this.request<User>('/api/v1/me', { method: 'PATCH', body: JSON.stringify(body) });
  }
  analyze(options: AnalysisOptions = {}, key = crypto.randomUUID()) {
    return this.request<Job>('/api/v1/analyses', {
      method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(options),
    });
  }
  job(id: string) { return this.request<Job>(`/api/v1/analyses/${encodeURIComponent(id)}`); }
  feed(offset = 0) { return this.request<Page<FeedItem>>(`/api/v1/feed?offset=${offset}`); }
  insight(id: number) { return this.request<Insight>(`/api/v1/insights/${id}`); }
  materials(kind: 'news' | 'bank_analytics' = 'news') {
    return this.request<Page<Material>>(`/api/v1/materials?kind=${kind}`);
  }
  material(id: number) { return this.request<Material>(`/api/v1/materials/${id}`); }
  question(id: number, question: string) {
    return this.request<{ answer: string; generation_mode: string; sources: unknown[] }>(
      `/api/v1/insights/${id}/questions`, { method: 'POST', body: JSON.stringify({ question }) });
  }
  feedback(id: number, rating: 'useful' | 'not_useful' | 'already_known', comment?: string) {
    return this.request(`/api/v1/insights/${id}/feedback`, { method: 'POST', body: JSON.stringify({ rating, comment }) });
  }
}
