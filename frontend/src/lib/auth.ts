import { businessIndustries, staffSizes, type UserProfile } from '../types/profile.ts';
import { normalizeProfile, validateProfile } from './profile.ts';

export const DEMO_SESSION_KEY = 'alfa-demo.session.v1';
export const DEMO_EMAIL = 'demo@example.com';
export const DEMO_PASSWORD = 'DemoAccess2026!';
export const DAY_MS = 24 * 60 * 60 * 1000;

export interface RegistrationFields {
  fullName: string;
  company: string;
  role: string;
  industry: string;
  staffSize: string;
  email: string;
  phone: string;
  password: string;
  consent: boolean;
}

export type RegistrationErrors = Partial<Record<keyof RegistrationFields, string>>;

export function passwordChecks(password: string): boolean[] {
  return [password.length >= 8 && password.length <= 128, /\p{L}/u.test(password), /\d/u.test(password)];
}

export function registrationProfile(fields: RegistrationFields): UserProfile {
  const company = fields.company.trim();
  const inn = /^\d{10}$/u.test(company) ? company : undefined;
  return normalizeProfile({
    fullName: fields.fullName, company: inn ? `Организация · ИНН ${inn}` : company,
    role: fields.role, email: fields.email, phone: fields.phone,
    ...(inn ? { companyInn: inn } : {}),
    ...(businessIndustries.some((value) => value === fields.industry) ? { industry: fields.industry as UserProfile['industry'] } : {}),
    ...(staffSizes.some((value) => value === fields.staffSize) ? { staffSize: fields.staffSize as UserProfile['staffSize'] } : {}),
  });
}

export function validateRegistration(fields: RegistrationFields): RegistrationErrors {
  const errors: RegistrationErrors = validateProfile(registrationProfile(fields));
  if (/^[\d\s]+$/u.test(fields.company.trim()) && !/^\d{10}$/u.test(fields.company.trim())) errors.company = 'ИНН организации должен содержать 10 цифр';
  if (fields.industry && !businessIndustries.some((value) => value === fields.industry)) errors.industry = 'Выберите отрасль из списка';
  if (fields.staffSize && !staffSizes.some((value) => value === fields.staffSize)) errors.staffSize = 'Выберите размер штата';
  if (!passwordChecks(fields.password).every(Boolean)) errors.password = 'От 8 до 128 символов, минимум одна буква и одна цифра';
  if (!fields.consent) errors.consent = 'Подтвердите, что создаёте демонстрационный профиль';
  return errors;
}

/** Доступ только к локальной демонстрации, не проверка реальной учётной записи. */
export function validateDemoLogin(email: string, password: string): string | null {
  return email.trim().toLowerCase() === DEMO_EMAIL && password === DEMO_PASSWORD
    ? null : 'Используйте демонстрационные данные, указанные под формой. Реальная авторизация пока не подключена.';
}

export function isDemoSession(value: unknown, now: number): boolean {
  if (typeof value !== 'object' || value === null) return false;
  const session = value as Record<string, unknown>;
  return session.kind === 'demo' && typeof session.expiresAt === 'number' && Number.isFinite(session.expiresAt)
    && session.expiresAt > now && session.expiresAt <= now + 30 * DAY_MS;
}

export function readDemoSession(): boolean {
  for (const type of ['sessionStorage', 'localStorage'] as const) {
    try {
      const raw = window[type].getItem(DEMO_SESSION_KEY);
      if (raw && isDemoSession(JSON.parse(raw), Date.now())) return true;
    } catch { /* Заблокированное/повреждённое хранилище не открывает приложение. */ }
  }
  return false;
}

export function startDemoSession(remember: boolean): void {
  const session = { kind: 'demo', expiresAt: Date.now() + (remember ? 30 * DAY_MS : DAY_MS) };
  const target = remember ? window.localStorage : window.sessionStorage;
  target.setItem(DEMO_SESSION_KEY, JSON.stringify(session));
  try { (remember ? window.sessionStorage : window.localStorage).removeItem(DEMO_SESSION_KEY); } catch { /* Другой storage может быть недоступен. */ }
}

export function clearDemoSession(): void {
  for (const type of ['sessionStorage', 'localStorage'] as const) {
    try { window[type].removeItem(DEMO_SESSION_KEY); } catch { /* Выход в памяти остаётся доступен. */ }
  }
}
