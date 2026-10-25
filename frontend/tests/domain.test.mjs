import test from 'node:test';
import assert from 'node:assert/strict';
import { parseRoute, initials, publicationLabel, toggleSelection, validateEntry, percent, safeExternalUrl, dateLabel, quoteSegments } from '../src/domain.ts';

test('routes preserve an insight identifier for an authenticated deep link', () => {
  assert.deepEqual(parseRoute('#/analysis/123'), { page: 'detail', id: '123' });
  assert.deepEqual(parseRoute('#/profile'), { page: 'profile' });
  assert.deepEqual(parseRoute('#/register'), { page: 'register' });
});
test('Cyrillic initials and Russian number endings', () => {
  assert.equal(initials('  егор   иванов '), 'ЕИ');
  assert.equal(initials(' '), '—');
  for (const count of [0, 5, 10, 11, 12, 14, 111]) assert.equal(publicationLabel(count), 'публикаций');
  assert.equal(publicationLabel(21), 'публикация');
  assert.equal(publicationLabel(22), 'публикации');
});
test('numeric material selection persists across pages and is limited to ten', () => {
  const original = new Set(); let selected = original;
  for (let id = 1; id <= 12; id++) selected = toggleSelection(selected, id);
  assert.equal(original.size, 0); assert.equal(selected.size, 10);
  selected = toggleSelection(selected, 5);
  assert.equal(selected.has(5), false); assert.equal(toggleSelection(selected, 12).size, 10);
});
test('login accepts a short existing password; registration enforces the server limits', () => {
  const values = { name: 'Аналитик', email: 'user@example.test', password: 'short', role: 'cfo', companyId: '1' };
  assert.deepEqual(validateEntry(values, false), {});
  assert.ok(validateEntry(values, true).password);
  assert.deepEqual(validateEntry({ ...values, password: '1234567890' }, true), {});
  assert.ok(validateEntry({ ...values, password: 'x'.repeat(129) }, true).password);
  assert.ok(validateEntry({ ...values, companyId: 'COMP-123' }, true).companyId);
  assert.ok(validateEntry({ ...values, role: 'arbitrary' }, true).role);
});
test('backend fractions become percentages without inflating factor indexes', () => {
  assert.equal(percent(0.7), 70); assert.equal(percent(0.045), 5);
  assert.equal(percent(5), 100); assert.equal(percent(-1), 0); assert.equal(percent(NaN), 0);
});
test('unknown dates stay unknown; displayed dates use Moscow time', () => {
  assert.equal(dateLabel(null), 'Дата не установлена');
  assert.equal(dateLabel('bad'), 'Дата не установлена');
  assert.match(dateLabel('2026-10-25T10:00:00Z'), /13:00.*МСК/u);
});
test('external references reject scripts, local paths, credentials and demo domains', () => {
  for (const url of ['javascript:alert(1)', 'file:///private/file.md', 'ml/data/source.md', 'https://demo.invalid/one', 'https://user:password@example.com/']) assert.equal(safeExternalUrl(url), undefined);
  assert.equal(safeExternalUrl('https://example.com/article', true), undefined);
  assert.equal(safeExternalUrl('https://example.com/article'), 'https://example.com/article');
});
test('exact source quotes remain highlighted across paragraph breaks without changing the body', () => {
  const body = 'Начало.\n\nПервый абзац.\n\nВторой абзац.\n\nКонец.';
  const quote = 'Первый абзац.\n\nВторой абзац.';
  const parts = quoteSegments(body, quote);
  assert.equal(parts.map((part) => part.text).join(''), body);
  assert.equal(parts.filter((part) => part.highlighted)[0].text, quote);
  assert.deepEqual(quoteSegments(body, ''), [{ text: body, highlighted: false }]);
});
