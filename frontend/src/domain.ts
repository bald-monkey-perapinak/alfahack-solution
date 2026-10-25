export const roleOptions = [
  { key: 'cfo', content: 'Финансовый директор' },
  { key: 'ceo', content: 'Генеральный директор' },
  { key: 'treasurer', content: 'Казначей' },
  { key: 'chief_accountant', content: 'Главный бухгалтер' },
  { key: 'owner', content: 'Собственник' },
] as const;
export type Role = (typeof roleOptions)[number]['key'];
export type Route = { page: 'login' | 'register' | 'analysis' | 'news' | 'profile' | 'detail'; id?: string };

export function parseRoute(hash: string): Route {
  const value = hash.replace(/^#\/?/u, '');
  if (value === 'login' || value === 'register' || value === 'news' || value === 'profile') return { page: value };
  if (value.startsWith('analysis/')) return { page: 'detail', id: value.slice(9) };
  return { page: 'analysis' };
}
export function roleLabel(role: Role): string { return roleOptions.find((option) => option.key === role)?.content || 'Не указано'; }
export function initials(name: string): string {
  return name.trim().split(/\s+/u).filter(Boolean).slice(0, 2).map((part) => Array.from(part)[0]).join('').toLocaleUpperCase('ru') || '—';
}
export function publicationLabel(count: number): string {
  const value = Math.abs(count) % 100;
  return value >= 11 && value <= 14 ? 'публикаций' : value % 10 === 1 ? 'публикация' : value % 10 >= 2 && value % 10 <= 4 ? 'публикации' : 'публикаций';
}
export function toggleSelection<T extends string | number>(selected: ReadonlySet<T>, id: T, limit = 10): Set<T> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else if (next.size < limit) next.add(id);
  return next;
}
export function validateEntry(values: { name: string; email: string; password: string; role: string; companyId: string }, register: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(values.email.trim())) errors.email = 'Проверьте адрес электронной почты';
  if (values.password.length < (register ? 10 : 1) || values.password.length > 128) errors.password = register ? 'От 10 до 128 символов' : 'Укажите пароль, не более 128 символов';
  if (register) {
    if (!values.name.trim()) errors.name = 'Укажите имя и фамилию';
    if (!values.companyId || !Number.isSafeInteger(Number(values.companyId)) || Number(values.companyId) <= 0) errors.companyId = 'Выберите компанию из каталога';
    if (!roleOptions.some((option) => option.key === values.role)) errors.role = 'Выберите аналитическую роль';
  }
  return errors;
}
export function dateLabel(value: string | null | undefined): string {
  if (!value) return 'Дата не установлена';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Дата не установлена';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Moscow' }).format(date) + ' МСК';
}
export function percent(value: number): number { return Math.round(Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0)) * 100); }
export function safeExternalUrl(value: string | null | undefined, demo = false): string | undefined {
  if (!value || demo) return undefined;
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.hostname === 'demo.invalid' || url.hostname.endsWith('.demo.invalid')) return undefined;
    return url.href;
  } catch { return undefined; }
}
export function asRecord(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
export function displayValue(value: unknown): string { return typeof value === 'string' && value.trim() ? value : 'Не указано'; }
export function quoteSegments(body: string, quote?: string): { text: string; highlighted: boolean }[] {
  if (!quote) return [{ text: body, highlighted: false }];
  return body.split(quote).flatMap((text, index) => index ? [{ text: quote, highlighted: true }, { text, highlighted: false }] : [{ text, highlighted: false }]);
}

// Refresh the feed for newly committed insights and once on a terminal transition.
export function jobPublicationKey(job: { status: string; insight_ids: number[] }): string {
  const ids = [...new Set(job.insight_ids)].sort((a, b) => a - b).join(',');
  return ids + (job.status === 'completed' || job.status === 'failed' ? `:${job.status}` : '');
}
