import test from 'node:test';
import assert from 'node:assert/strict';
import { DEMO_EMAIL, DEMO_PASSWORD, DEMO_SESSION_KEY, DAY_MS, validateDemoLogin, validateRegistration,
  registrationProfile, passwordChecks, isDemoSession, readDemoSession, startDemoSession, clearDemoSession } from '../src/lib/auth.ts';

const fields = { fullName: 'Иванов Иван', company: 'ООО «Пример»', role: 'Главный казначей', industry: 'Производство',
  staffSize: 'до 50 сотрудников', email: 'ivan@example.com', phone: '', password: 'Example2026!', consent: true };

test('регистрация принимает свободную должность и необязательный телефон', () => {
  assert.deepEqual(validateRegistration(fields), {});
  assert.deepEqual(validateRegistration({ ...fields, industry: '', staffSize: '' }), {});
  assert.ok(validateRegistration({ ...fields, role: ' ' }).role);
  assert.ok(validateRegistration({ ...fields, phone: '123' }).phone);
});

test('регистрация проверяет профиль, ИНН, пароль, контекст и подтверждение демо-режима', () => {
  for (const [key, value] of [['fullName', 'Иван'], ['company', '123'], ['role', ''], ['email', 'bad'],
    ['password', '12345678'], ['consent', false], ['industry', 'unknown'], ['staffSize', 'unknown']]) {
    assert.ok(validateRegistration({ ...fields, [key]: value })[key], key);
  }
  assert.deepEqual(passwordChecks('Example2026!'), [true, true, true]);
  assert.deepEqual(passwordChecks(''), [false, false, false]);
  assert.equal(passwordChecks('a1'.repeat(65))[0], false);
});

test('передача профиля не включает пароль и согласие, сохраняет контекст компании', () => {
  const result = registrationProfile({ ...fields, company: '7700000001', role: ' Главный казначей ' });
  assert.equal(result.companyInn, '7700000001');
  assert.equal(result.company, 'Организация · ИНН 7700000001');
  assert.equal(result.industry, fields.industry);
  assert.equal(result.staffSize, fields.staffSize);
  assert.equal(result.role, fields.role);
  assert.equal('password' in result, false);
  assert.equal('consent' in result, false);
});

test('демо-вход проверяет только заранее опубликованную демо-пару', () => {
  assert.equal(validateDemoLogin(DEMO_EMAIL, DEMO_PASSWORD), null);
  assert.equal(validateDemoLogin(' DEMO@EXAMPLE.COM ', DEMO_PASSWORD), null);
  assert.ok(validateDemoLogin(DEMO_EMAIL, 'wrong'));
  assert.ok(validateDemoLogin('someone@example.com', DEMO_PASSWORD));
});

test('флаг демо-доступа имеет срок и не принимает произвольную структуру', () => {
  const now = Date.now();
  assert.equal(isDemoSession({ kind: 'demo', expiresAt: now + DAY_MS }, now), true);
  for (const value of [null, true, {}, { kind: 'demo', expiresAt: now }, { kind: 'demo', expiresAt: now - 1 },
    { kind: 'demo', expiresAt: now + 31 * DAY_MS }, { kind: 'demo', expiresAt: Infinity }, { kind: 'real', expiresAt: now + DAY_MS }]) {
    assert.equal(isDemoSession(value, now), false);
  }
});

test('сессия, запоминание, выход и поврежденное хранилище не сохраняют пароли', () => {
  const previousWindow = globalThis.window;
  const makeStorage = () => {
    const data = new Map();
    return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
  };
  try {
    globalThis.window = { localStorage: makeStorage(), sessionStorage: makeStorage() };
    assert.equal(readDemoSession(), false);
    startDemoSession(false);
    assert.equal(readDemoSession(), true);
    assert.equal(window.localStorage.getItem(DEMO_SESSION_KEY), null);
    assert.deepEqual(Object.keys(JSON.parse(window.sessionStorage.getItem(DEMO_SESSION_KEY))).sort(), ['expiresAt', 'kind']);
    startDemoSession(true);
    assert.equal(window.sessionStorage.getItem(DEMO_SESSION_KEY), null);
    assert.equal(readDemoSession(), true);
    clearDemoSession();
    assert.equal(readDemoSession(), false);
    window.localStorage.setItem(DEMO_SESSION_KEY, '{');
    assert.equal(readDemoSession(), false);
    globalThis.window = { get localStorage() { throw new Error('blocked'); }, get sessionStorage() { throw new Error('blocked'); } };
    assert.equal(readDemoSession(), false);
    assert.doesNotThrow(clearDemoSession);
    assert.throws(() => startDemoSession(false));
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
