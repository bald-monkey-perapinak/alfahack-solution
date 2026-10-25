import type { Role } from '../domain.ts';

// Public DTOs follow contracts/openapi.json and backend/app/responses.py.
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type User = { id: number; name: string; email: string; role: Role; org_id: number };
export type Session = { access_token: string; token_type: 'bearer'; expires_at: string; user?: User | null };
export type Registration = { email: string; password: string; name: string; role: Role; organization_id: number };
export type Organization = { id: number; name: string; synthetic_u: string | null; industry: string | null; region: string | null };
export type Company = Omit<Organization, 'name'> & {
  name: string | null; city: string | null; okved_code: string | null;
  has_loans: boolean | null; has_leasing: boolean | null; has_deposits: boolean | null;
  has_guarantees: boolean | null; has_factoring: boolean | null; has_foreign_trade: boolean | null;
  foreign_trade_countries: string[]; profile_data: Record<string, unknown>;
};
export type CompanyProfile = { company_id: string; observed: Record<string, unknown>; declared: Record<string, unknown>; inferred: Record<string, unknown>; exposures: Record<string, number>; confidence: number };
export type OrganizationContext = { organization: Company; profile: CompanyProfile };
export type Counterparty = { id: number; counterparty_id: number; counterparty_name: string; relation_type: 'supplier' | 'buyer' | 'partner' | 'other'; evidence: string; dependency_weight: number | null };
export type Counterparties = { items: Counterparty[]; note: string };
export type GenerationMode = 'offline' | 'live';
export type AnalysisOptions = { material_ids?: number[]; max_events: number };
export type Job = {
  id: string; status: 'pending' | 'running' | 'completed' | 'failed'; parameters: AnalysisOptions;
  created_at: string; finished_at: string | null; error_code: string | null;
  summary: { processed?: number; created?: number; skipped?: number }; insight_ids: number[];
};
export type FeedItem = { id: number; title: string; relevance_score: number; confidence: number; created_at: string; primary_material_id: number; generation_mode: GenerationMode; is_demo: boolean; warnings: string[] };
export type Evidence = { id: number; insight_id: number; material_id: number; section: string; claim: string; quote: string; locator: string | null; source_title: string; source_ref: string; published_at: string | null };
export type Insight = {
  id: number; run_id: number; primary_material_id: number; title: string; facts: string;
  bank_view: string | null; interpretation: string; relevance_reason: string; confidence: number; relevance_score: number;
  risks: string[]; opportunities: string[]; suggested_actions: { type?: string; label?: string; rationale?: string; priority?: number }[];
  created_at: string; target_role: Role; model_name: string; company_context: Record<string, unknown>;
  payload: { generation_mode?: GenerationMode; is_demo?: boolean; warnings?: string[]; [key: string]: unknown };
  evidence: Evidence[]; steps: { tool: string; at?: string; result: unknown }[];
};
export type Material = { id: number; title: string; summary: string | null; published_at: string | null; material_type: 'news' | 'bank_analytics'; source_ref: string; is_demo: boolean };
export type MaterialDetail = Material & { body: string; source_name: string; source_id: number };
export type QuestionAnswer = { answer: string; generation_mode: GenerationMode; sources: { material_id: number; quote: string; section: string }[] };
export type Rating = 'useful' | 'not_useful' | 'already_known';
export type Feedback = { id: number; insight_id: number; user_id: number; rating: Rating; comment: string | null; updated_at: string };
export type Roles = { items: { id: Role; name: string }[] };
export type Health = { status: string; generation_mode: GenerationMode };
