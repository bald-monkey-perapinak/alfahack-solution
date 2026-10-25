import test from 'node:test';
import assert from 'node:assert/strict';
import { getInitials, normalizeProfile, validateProfile, isUserProfile, isCounterpartyList,
  prepareCounterparty, readStoredValue } from '../src/lib/profile.ts';

const profile = { fullName: 'Иванов Иван Иванович', company: 'ООО «Пример»',
  role: 'Финансовый директор', email: 'ivan@example.com', phone: '+7 (999) 000-24-11' };

test('инициалы из фамилии и имени, без отчества; пробелы и пустая строка', () => {
  assert.equal(getInitials('Константинопольский Константин К.'), 'КК');
  assert.equal(getInitials('  иванов   пётр сергеевич '), 'ИП');
  assert.equal(getInitials('Иванов-Петров Иван'), 'ИИ');
  assert.equal(getInitials('Иванов'), 'И');
  assert.equal(getInitials('  '), '—');
});

test('нормализация не меняет исходный профиль', () => {
  const input = { ...profile, fullName: '  Иванов   Иван  ', email: ' ivan@example.com ' };
  assert.deepEqual(normalizeProfile(input), { ...profile, fullName: 'Иванов Иван' });
  assert.equal(input.email, ' ivan@example.com ');
});

test('проверка обязательных полей, e-mail, должности и телефона', () => {
  assert.deepEqual(validateProfile(profile), {});
  const errors = validateProfile({ fullName: 'Иван', company: ' ', role: ' ', email: 'bad', phone: 'не телефон' });
  assert.deepEqual(Object.keys(errors).sort(), ['company', 'email', 'fullName', 'phone', 'role']);
  assert.ok(validateProfile({ ...profile, phone: '123' }).phone);
  assert.ok(validateProfile({ ...profile, email: 'bad@local' }).email);
  assert.ok(validateProfile({ ...profile, company: 'a'.repeat(201) }).company);
  assert.deepEqual(validateProfile({ ...profile, role: 'Главный казначей', phone: '' }), {});
  assert.ok(validateProfile({ ...profile, role: 'x'.repeat(121) }).role);
});

test('поврежденные данные профиля и контрагентов из хранилища отклоняются', () => {
  assert.equal(isUserProfile(profile), true);
  for (const value of [null, [], 'text', { ...profile, phone: 123 }, { ...profile, role: '' }, { ...profile, industry: 7 }]) assert.equal(isUserProfile(value), false);
  assert.equal(isUserProfile({ ...profile, role: 'Директор по развитию' }), true);
  const entry = { id: 'one', name: 'Компания', inn: '7700000001', kind: 'supplier' };
  assert.equal(isCounterpartyList([entry]), true);
  assert.equal(isCounterpartyList([]), true);
  for (const value of [null, {}, [entry, entry], [{ ...entry, inn: '12' }], [{ ...entry, kind: 'unknown' }]]) assert.equal(isCounterpartyList(value), false);
});

test('добавление по имени или ИНН не выдумывает данные реестра', () => {
  assert.deepEqual(prepareCounterparty('  ООО   «Пример» ', []).entry, { name: 'ООО «Пример»', kind: 'other' });
  assert.deepEqual(prepareCounterparty('7700 0000 01', []).entry, { name: 'Контрагент по ИНН', inn: '7700000001', kind: 'other' });
  assert.equal(prepareCounterparty('123456789012', []).entry.inn, '123456789012');
  for (const query of ['', ' ', '1', '123456789', '12345678901', 'x'.repeat(201)]) assert.ok(prepareCounterparty(query, []).error);
});

test('повторное добавление по имени или ИНН запрещено; исходный массив не меняется', () => {
  const current = [{ id: 'one', name: 'ООО «Пример»', inn: '7700000001', kind: 'supplier' }];
  assert.ok(prepareCounterparty('ооо «пример»', current).error);
  assert.ok(prepareCounterparty('7700000001', current).error);
  assert.equal(current.length, 1);
});

test('хранилище: корректные данные, поврежденный JSON, неверная структура и запрет доступа', () => {
  const previousWindow = globalThis.window;
  try {
    for (const raw of [null, '{', '{"fullName":7}']) {
      globalThis.window = { localStorage: { getItem: () => raw } };
      assert.equal(readStoredValue('profile', profile, isUserProfile), profile);
    }
    globalThis.window = { localStorage: { getItem: () => JSON.stringify(profile) } };
    assert.deepEqual(readStoredValue('profile', null, isUserProfile), profile);
    globalThis.window = { get localStorage() { throw new Error('blocked'); } };
    assert.equal(readStoredValue('profile', profile, isUserProfile), profile);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
