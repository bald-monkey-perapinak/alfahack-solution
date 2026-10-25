import { businessIndustries, staffSizes, type Counterparty, type ProfileErrors, type UserProfile } from '../types/profile.ts';

export const PROFILE_STORAGE_KEY = 'alfa-demo.profile.v1';
export const COUNTERPARTIES_STORAGE_KEY = 'alfa-demo.counterparties.v1';

export function getInitials(fullName: string): string {
  return fullName.trim().split(/\s+/u).filter(Boolean).slice(0, 2)
    .map((part) => Array.from(part)[0]).join('').toLocaleUpperCase('ru') || '—';
}

export function normalizeProfile(profile: UserProfile): UserProfile {
  return {
    ...profile,
    fullName: profile.fullName.trim().replace(/\s+/gu, ' '),
    company: profile.company.trim(),
    role: profile.role.trim(),
    email: profile.email.trim(),
    phone: profile.phone.trim(),
  };
}

export function validateProfile(profile: UserProfile): ProfileErrors {
  const errors: ProfileErrors = {};
  if (profile.fullName.trim().split(/\s+/u).filter(Boolean).length < 2) errors.fullName = 'Укажите фамилию и имя';
  if (profile.fullName.length > 160) errors.fullName = 'Не более 160 символов';
  if (!profile.company.trim()) errors.company = 'Укажите название компании';
  if (profile.company.length > 200) errors.company = 'Не более 200 символов';
  if (!profile.role.trim()) errors.role = 'Укажите должность';
  if (profile.role.length > 120) errors.role = 'Не более 120 символов';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(profile.email.trim()) || profile.email.length > 254) errors.email = 'Проверьте адрес электронной почты';
  const digits = profile.phone.replace(/\D/gu, '');
  if (profile.phone.trim() && (!/^[+\d\s()\-]+$/u.test(profile.phone) || digits.length < 10 || digits.length > 15)) errors.phone = 'Укажите телефон: от 10 до 15 цифр';
  return errors;
}

export function isUserProfile(value: unknown): value is UserProfile {
  if (typeof value !== 'object' || value === null) return false;
  const profile = value as Record<string, unknown>;
  return ['fullName', 'company', 'role', 'email', 'phone'].every((key) => typeof profile[key] === 'string')
    && (profile.industry === undefined || businessIndustries.some((value) => value === profile.industry))
    && (profile.staffSize === undefined || staffSizes.some((value) => value === profile.staffSize))
    && (profile.companyInn === undefined || (typeof profile.companyInn === 'string' && /^\d{10}$/u.test(profile.companyInn)))
    && Object.keys(validateProfile(profile as unknown as UserProfile)).length === 0;
}

export function isCounterpartyList(value: unknown): value is Counterparty[] {
  if (!Array.isArray(value)) return false;
  const ids = new Set<string>();
  return value.every((item: unknown) => {
    if (typeof item !== 'object' || item === null) return false;
    const entry = item as Record<string, unknown>;
    if (typeof entry.id !== 'string' || !entry.id || ids.has(entry.id)
      || typeof entry.name !== 'string' || !entry.name.trim() || entry.name.length > 200
      || typeof entry.kind !== 'string' || !['supplier', 'logistics', 'buyer', 'other'].includes(entry.kind)
      || (entry.inn !== undefined && (typeof entry.inn !== 'string' || !/^(\d{10}|\d{12})$/u.test(entry.inn)))) return false;
    ids.add(entry.id);
    return true;
  });
}

/** Только локальное добавление: не ищет организацию по ИНН и не проверяет её надежность. */
export function prepareCounterparty(query: string, current: readonly Counterparty[]):
  { entry: Omit<Counterparty, 'id'>; error?: never } | { error: string; entry?: never } {
  const text = query.trim().replace(/\s+/gu, ' ');
  if (!text) return { error: 'Введите ИНН или название организации' };
  if (text.length > 200) return { error: 'Название должно быть не длиннее 200 символов' };
  const numeric = /^[\d\s]+$/u.test(text);
  const inn = numeric ? text.replace(/\s/gu, '') : undefined;
  if (inn && !/^(\d{10}|\d{12})$/u.test(inn)) return { error: 'ИНН должен содержать 10 или 12 цифр' };
  if (!inn && text.length < 2) return { error: 'Введите название организации' };
  if (current.some((item) => inn ? item.inn === inn : item.name.toLocaleLowerCase('ru') === text.toLocaleLowerCase('ru'))) {
    return { error: 'Этот контрагент уже добавлен' };
  }
  return { entry: { name: inn ? 'Контрагент по ИНН' : text, ...(inn ? { inn } : {}), kind: 'other' } };
}

export function readStoredValue<T>(key: string, fallback: T, isValid: (value: unknown) => value is T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    const value: unknown = JSON.parse(raw);
    return isValid(value) ? value : fallback;
  } catch {
    return fallback;
  }
}
