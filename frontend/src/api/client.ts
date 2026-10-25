import type { AnalysisOptions, Counterparties, Feedback, FeedItem, Health, Insight, Job, Material, MaterialDetail, Organization, OrganizationContext, Page, QuestionAnswer, Rating, Registration, Roles, Session, User } from './types.ts';

type ValidationField = { loc: (string | number)[]; msg: string; type: string };
export class ApiError extends Error {
  status: number;
  code: string;
  fields: ValidationField[];
  retryAfter: number | null;
  requestId: string | null;
  constructor(status: number, code: string, fields: ValidationField[] = [], retryAfter: number | null = null, requestId: string | null = null) {
    super(code); this.name = 'ApiError'; this.status = status; this.code = code;
    this.fields = fields; this.retryAfter = retryAfter; this.requestId = requestId;
  }
}
export function isAborted(error: unknown): boolean { return error instanceof Error && error.name === 'AbortError'; }
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Не удалось связаться с сервером. Проверьте подключение и повторите попытку.';
  const messages: Record<string, string> = {
    llm_invalid_output: 'Ответ модели не соответствует формату анализа.', insight_verification_failed: 'Ответ модели не прошёл проверку обоснованности.',
    llm_timeout: 'Модель не ответила за отведённое время.', llm_transport_error: 'Соединение с моделью прервано.',
    llm_budget_exceeded: 'Лимит бюджета LLM исчерпан.', llm_auth_failed: 'Провайдер отклонил ключ LLM.',
    llm_rate_limited: 'Провайдер временно ограничил запросы.', llm_provider_unavailable: 'Сервис модели временно недоступен.',
    invalid_credentials: 'Неверный e-mail или пароль.', email_already_registered: 'Этот e-mail уже зарегистрирован. Войдите в аккаунт.',
    organizer_company_required: 'Выберите компанию U_… в профиле и сохраните изменения.',
    organizer_data_not_ready: 'Данные организаторов ещё загружаются.',
    organization_not_found: 'Компания больше недоступна. Выберите другую компанию из каталога.',
    authentication_required: 'Войдите в аккаунт, чтобы продолжить.', invalid_or_expired_token: 'Сессия завершена. Войдите повторно.',
    analysis_already_in_progress: 'У вас уже есть незавершённые задания. Дождитесь их завершения.',
    idempotency_key_conflict: 'Параметры запуска изменились. Закройте окно и запустите анализ заново.',
    news_material_not_found: 'Одна из выбранных публикаций недоступна. Обновите список и выберите материалы заново.',
    insight_not_found: 'Анализ не найден или недоступен для вашего аккаунта.', analysis_not_found: 'Задание не найдено или недоступно для вашего аккаунта.',
    material_not_found: 'Источник не найден или недоступен.', database_not_ready: 'База данных временно недоступна. Повторите попытку позже.',
    validation_error: 'Проверьте заполненные поля.', request_timeout: 'Сервер не ответил вовремя. Повторите попытку.',
    network_error: 'Не удалось связаться с сервером. Проверьте, запущен ли API, и повторите попытку.',
    invalid_response: 'Сервер вернул неожиданный ответ. Повторите попытку.',
  };
  if (error.status === 429) return `Слишком много запросов. ${error.retryAfter ? `Повторите через ${error.retryAfter} с.` : 'Подождите немного и повторите попытку.'}`;
  return messages[error.code] || (error.status === 401 ? 'Сессия завершена. Войдите повторно.' : error.status === 404 ? 'Данные не найдены или недоступны.' : error.status === 502 ? 'Не удалось получить проверенный ответ аналитической модели. Повторите попытку позже.' : error.status === 403 ? 'Действие недоступно для вашего аккаунта.' : 'Сервис временно недоступен. Повторите попытку позже.');
}
export function validationErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const aliases: Record<string, string> = { organization_id: 'companyId' };
  return Object.fromEntries(error.fields.map((field) => {
    const name = String(field.loc[field.loc.length - 1]);
    return [aliases[name] || name, 'Проверьте значение поля'];
  }));
}

export class AnalyticsApi {
  private token: string | null = null;
  private base: string;
  private transport: typeof fetch;
  onUnauthorized: (() => void) | undefined;
  constructor(base = '', transport: typeof fetch = (input, init) => fetch(input, init)) {
    this.base = base.replace(/\/+$/u, ''); this.transport = transport;
  }
  setToken(token: string | null) { this.token = token; }
  async request<T>(path: string, init: RequestInit = {}, options: { public?: boolean; timeout?: number } = {}): Promise<T> {
    const token = options.public ? null : this.token;
    const headers = new Headers(init.headers);
    if (init.body) headers.set('Content-Type', 'application/json');
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (init.signal?.aborted) controller.abort();
    else init.signal?.addEventListener('abort', abort, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, options.timeout || 20000);
    try {
      const response = await this.transport(`${this.base}${path}`, { ...init, headers, signal: controller.signal, credentials: 'omit' });
      const data = response.status === 204 ? undefined : await response.json().catch(() => undefined);
      if (!response.ok) {
        const seconds = Number(response.headers.get('Retry-After'));
        const error = new ApiError(response.status, data?.error?.code || 'request_failed', data?.error?.fields || [], Number.isFinite(seconds) && seconds > 0 ? seconds : null, data?.error?.request_id || response.headers.get('X-Request-ID'));
        if (response.status === 401 && token && this.token === token) { this.token = null; this.onUnauthorized?.(); }
        throw error;
      }
      if (response.status !== 204 && data === undefined) throw new ApiError(502, 'invalid_response');
      return data as T;
    } catch (error) {
      if (timedOut) throw new ApiError(0, 'request_timeout');
      if (error instanceof ApiError || isAborted(error)) throw error;
      throw new ApiError(0, 'network_error');
    } finally { clearTimeout(timer); init.signal?.removeEventListener('abort', abort); }
  }
  health(signal?: AbortSignal) { return this.request<Health>('/health/ready', { signal }, { public: true }); }
  roles(signal?: AbortSignal) { return this.request<Roles>('/api/v1/roles', { signal }, { public: true }); }
  organizations(q = '', offset = 0, signal?: AbortSignal) { return this.request<Page<Organization>>(`/api/v1/organizations?q=${encodeURIComponent(q)}&limit=20&offset=${offset}`, { signal }, { public: true }); }
  register(body: Registration, signal?: AbortSignal) { return this.request<Session>('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(body), signal }, { public: true }); }
  login(email: string, password: string, signal?: AbortSignal) { return this.request<Session>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email, password }), signal }, { public: true }); }
  async logout() { await this.request<void>('/api/v1/auth/logout', { method: 'POST' }); this.setToken(null); }
  me(signal?: AbortSignal) { return this.request<User>('/api/v1/me', { signal }); }
  updateMe(body: Pick<User, 'name' | 'role'> & { organization_id?: number }, signal?: AbortSignal) { return this.request<User>('/api/v1/me', { method: 'PATCH', body: JSON.stringify(body), signal }); }
  organization(signal?: AbortSignal) { return this.request<OrganizationContext>('/api/v1/me/organization', { signal }); }
  counterparties(signal?: AbortSignal) { return this.request<Counterparties>('/api/v1/me/counterparties?limit=20', { signal }); }
  analyze(body: AnalysisOptions, key: string, signal?: AbortSignal) { return this.request<Job>('/api/v1/analyses', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(body), signal }); }
  job(id: string, signal?: AbortSignal) { return this.request<Job>(`/api/v1/analyses/${encodeURIComponent(id)}`, { signal }); }
  feed(offset = 0, limit = 6, signal?: AbortSignal) { return this.request<Page<FeedItem>>(`/api/v1/feed?limit=${limit}&offset=${offset}`, { signal }); }
  insight(id: number, signal?: AbortSignal) { return this.request<Insight>(`/api/v1/insights/${id}`, { signal }); }
  materials(offset = 0, limit = 6, signal?: AbortSignal) { return this.request<Page<Material>>(`/api/v1/materials?kind=news&limit=${limit}&offset=${offset}`, { signal }); }
  material(id: number, signal?: AbortSignal) { return this.request<MaterialDetail>(`/api/v1/materials/${id}`, { signal }); }
  question(id: number, question: string, signal?: AbortSignal) { return this.request<QuestionAnswer>(`/api/v1/insights/${id}/questions`, { method: 'POST', body: JSON.stringify({ question }), signal }, { timeout: 390000 }); }
  feedback(id: number, rating: Rating, comment?: string, signal?: AbortSignal) { return this.request<Feedback>(`/api/v1/insights/${id}/feedback`, { method: 'POST', body: JSON.stringify({ rating, ...(comment?.trim() ? { comment: comment.trim() } : {}) }), signal }); }
}
