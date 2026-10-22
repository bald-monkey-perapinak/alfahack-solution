import assert from 'node:assert/strict';
import test from 'node:test';
import { arrangeNewsContainers } from '../src/lib/news-layout/arrangeNewsContainers.ts';
import { composeNewsContainers } from '../src/lib/news-layout/composeNewsContainers.ts';

const formats = ['hero', 'duo', 'trio', 'quartet'];
const sizes = { hero: 1, duo: 2, trio: 3, quartet: 4 };

function makeContainers(variants, options = {}) {
  const { prefix = 'c', sourceGroupId = 'g', placement = 'group' } = options;
  return variants.map((variant, index) => ({
    id: `${prefix}-${index}`,
    sourceGroupId,
    title: 'Новости',
    variant,
    placement,
    reason: variant === 'hero' ? 'important' : 'compact',
    items: Array.from({ length: sizes[variant] }, (_, itemIndex) => ({
      id: `${prefix}-${index}-${itemIndex}`,
      importance: 90 - itemIndex,
      title: 'Пример', summary: '',
      source: { name: 'Пример', url: 'https://example.com/' },
      publishedAt: '2026-10-22T10:00:00+03:00',
      topic: 'Макроэкономика',
      urgency: placement === 'urgent' ? 'urgent' : 'normal',
      isFavorite: false, analysisStatus: 'ready',
    })),
  }));
}

function longestRun(variants) {
  let best = 0;
  let run = 0;
  let previous;
  for (const variant of variants) {
    run = variant === previous ? run + 1 : 1;
    previous = variant;
    best = Math.max(best, run);
  }
  return best;
}

const variantsOf = (containers) => containers.map(({ variant }) => variant);

test('пустой вход, один контейнер и единственный доступный формат', () => {
  assert.deepEqual(arrangeNewsContainers([]), []);
  for (const variants of [['hero'], ['quartet', 'quartet', 'quartet']]) {
    const input = makeContainers(variants);
    const output = arrangeNewsContainers(input);
    assert.deepEqual(output, input);
    assert.notEqual(output, input);
  }
});

test('три Quartet разделяются другими форматами при их наличии', () => {
  const input = makeContainers(['quartet', 'quartet', 'quartet', 'duo', 'trio']);
  assert.deepEqual(variantsOf(arrangeNewsContainers(input)), ['quartet', 'duo', 'quartet', 'trio', 'quartet']);
});

test('Hero чередуются с компактными контейнерами, первый блок закреплён', () => {
  const input = makeContainers(['hero', 'hero', 'hero', 'duo', 'trio', 'trio', 'quartet']);
  const output = arrangeNewsContainers(input);
  assert.equal(output[0], input[0]);
  assert.deepEqual(variantsOf(output), ['hero', 'duo', 'hero', 'trio', 'hero', 'trio', 'quartet']);
});

test('редкие разделители распределяются по длинной группе, а не расходуются сразу', () => {
  const input = makeContainers([...Array(3).fill('hero'), ...Array(10).fill('quartet')]);
  const output = arrangeNewsContainers(input, { maxShift: input.length });
  // После первого Hero осталось 2 разделителя для 10 Quartet: минимум ceil(10/3)=4.
  assert.equal(longestRun(variantsOf(output)), 4);
  assert.equal(output[0], input[0]);
});

test('maxShift ограничивает продвижение и опускание; 0 сохраняет исходный порядок', () => {
  const input = makeContainers([...Array(18).fill('quartet'), 'hero', 'duo', 'trio']);
  for (const maxShift of [0, 1, 2, 4, 10]) {
    const output = arrangeNewsContainers(input, { maxShift });
    output.forEach((container, index) => {
      assert.ok(Math.abs(input.indexOf(container) - index) <= maxShift);
    });
  }
  assert.deepEqual(arrangeNewsContainers(input, { maxShift: 0 }), input);
  // Дальние разделители не протаскиваются в начало вопреки лимиту.
  assert.deepEqual(variantsOf(arrangeNewsContainers(input)).slice(0, 5), Array(5).fill('quartet'));
});

test('не изменяет вход, объекты, состав и порядок новостей внутри контейнеров', () => {
  const input = makeContainers(['hero', 'hero', 'quartet', 'quartet', 'duo', 'trio']);
  const before = structuredClone(input);
  input.forEach((container) => {
    container.items.forEach(Object.freeze);
    Object.freeze(container.items);
    Object.freeze(container);
  });
  Object.freeze(input);
  const output = arrangeNewsContainers(input);
  assert.deepEqual(input, before);
  assert.equal(output.length, input.length);
  assert.equal(new Set(output).size, input.length);
  assert.ok(output.every((container) => input.includes(container)));
  assert.deepEqual(output.flatMap(({ items }) => items.map(({ id }) => id)).sort(),
    input.flatMap(({ items }) => items.map(({ id }) => id)).sort());
});

test('сохраняет относительный порядок важности контейнеров одного формата', () => {
  const input = makeContainers(['hero', 'hero', 'hero', 'duo', 'duo', 'trio', 'trio', 'quartet', 'quartet']);
  const output = arrangeNewsContainers(input);
  for (const variant of formats) {
    assert.deepEqual(output.filter((item) => item.variant === variant), input.filter((item) => item.variant === variant));
  }
});

test('не смешивает разные sourceGroupId, даже если placement и заголовки совпадают', () => {
  const first = makeContainers(['quartet', 'quartet', 'quartet', 'duo', 'trio'], { prefix: 'a', sourceGroupId: 'a' });
  const second = makeContainers(['hero', 'hero', 'duo'], { prefix: 'b', sourceGroupId: 'b' });
  const output = arrangeNewsContainers([...first, ...second]);
  assert.deepEqual(output.slice(0, first.length), arrangeNewsContainers(first));
  assert.deepEqual(output.slice(first.length), arrangeNewsContainers(second));
});

test('urgent, highlights и group остаются самостоятельными разделами', () => {
  const urgent = makeContainers(['hero', 'hero', 'duo'], { prefix: 'u', placement: 'urgent' });
  const highlights = makeContainers(['hero', 'hero', 'hero'], { prefix: 'h', placement: 'highlights' });
  const regular = makeContainers(['quartet', 'quartet', 'trio'], { prefix: 'g' });
  const output = arrangeNewsContainers([...urgent, ...highlights, ...regular]);
  assert.deepEqual(output.map(({ placement }) => placement), [
    ...Array(urgent.length).fill('urgent'), ...Array(highlights.length).fill('highlights'), ...Array(regular.length).fill('group'),
  ]);
  assert.deepEqual(output.slice(urgent.length, urgent.length + highlights.length), highlights);
  assert.equal(output[0], urgent[0]);
  assert.equal(output[urgent.length + highlights.length], regular[0]);
});

test('повторяющиеся группы не перемещаются через промежуточные разделы', () => {
  const a1 = makeContainers(['hero', 'hero'], { prefix: 'a1', sourceGroupId: 'a' });
  const b = makeContainers(['duo'], { prefix: 'b', sourceGroupId: 'b' });
  const a2 = makeContainers(['quartet', 'trio'], { prefix: 'a2', sourceGroupId: 'a' });
  assert.deepEqual(arrangeNewsContainers([...a1, ...b, ...a2]), [...a1, ...b, ...a2]);
});

test('совместим с реальной компоновкой: разбиение не меняется, срочные не уходят в highlights', () => {
  const scores = [98, 93, 88, 77, 71, 49, 38, 35, 32, 22, 19, 16, 12, 8, 4];
  const news = scores.flatMap((importance, index) => ['urgent', 'normal'].map((urgency) => ({
    ...makeContainers(['hero'])[0].items[0], id: `${urgency}-${index}`, importance, urgency,
  })));
  const composed = composeNewsContainers(news, { groupId: 'economy' });
  const arranged = arrangeNewsContainers(composed);
  assert.equal(arranged.length, composed.length);
  assert.ok(arranged.every((container) => composed.includes(container)));
  assert.ok(arranged.every((container) => container.items.every((item) =>
    (item.urgency === 'urgent') === (container.placement === 'urgent'))));
  assert.ok(arranged.every(({ sourceGroupId }) => sourceGroupId === 'economy'));
  const urgent = arranged.filter(({ placement }) => placement === 'urgent');
  assert.equal(longestRun(variantsOf(urgent)), 1);
});

test('результат детерминирован; неверные настройки и повторные id отклоняются', () => {
  const input = makeContainers(['hero', 'hero', 'duo', 'trio', 'quartet']);
  assert.deepEqual(arrangeNewsContainers(input), arrangeNewsContainers(input));
  for (const maxShift of [-1, 1.5, NaN, Infinity, '4', Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => arrangeNewsContainers(input, { maxShift }), /maxShift/);
  }
  assert.throws(() => arrangeNewsContainers([input[0], input[0]]), /Повторяющийся id/);
});

// Независимый перебор всех допустимых последовательностей для маленьких групп.
function optimalLongestRun(variants) {
  if (!variants.length) return 0;
  const counts = formats.map((format) => variants.filter((item) => item === format).length);
  const first = formats.indexOf(variants[0]);
  counts[first]--;
  const memo = new Map();
  function search(previous, run) {
    const key = `${counts.join(',')}:${previous}:${run}`;
    if (memo.has(key)) return memo.get(key);
    let best = Infinity;
    for (let variant = 0; variant < formats.length; variant++) {
      if (!counts[variant]) continue;
      const nextRun = previous === variant ? run + 1 : 1;
      counts[variant]--;
      best = Math.min(best, Math.max(nextRun, search(variant, nextRun)));
      counts[variant]++;
    }
    const result = best === Infinity ? 0 : best;
    memo.set(key, result);
    return result;
  }
  return Math.max(1, search(first, 1));
}

test('при свободных перестановках минимизирует максимальную серию: проверка полным перебором', () => {
  for (let h = 0; h <= 2; h++) for (let d = 0; d <= 2; d++) {
    for (let t = 0; t <= 2; t++) for (let q = 0; q <= 2; q++) {
      const variants = [...Array(h).fill('hero'), ...Array(d).fill('duo'), ...Array(t).fill('trio'), ...Array(q).fill('quartet')];
      const output = arrangeNewsContainers(makeContainers(variants), { maxShift: variants.length });
      assert.equal(longestRun(variantsOf(output)), optimalLongestRun(variants), variants.join(','));
    }
  }
});

test('на 1000 группах сохраняет блоки, границы сдвига, первый блок и порядок внутри форматов', () => {
  let seed = 12345;
  for (let count = 0; count < 100; count++) for (let run = 0; run < 10; run++) {
    const variants = Array.from({ length: count }, () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return formats[(seed >>> 16) % formats.length];
    });
    const input = makeContainers(variants);
    const before = structuredClone(input);
    const maxShift = run % 7;
    const output = arrangeNewsContainers(input, { maxShift });
    assert.deepEqual(input, before);
    assert.equal(output.length, input.length);
    assert.equal(new Set(output).size, input.length);
    assert.equal(output[0], input[0]);
    output.forEach((container, index) => assert.ok(Math.abs(input.indexOf(container) - index) <= maxShift));
    for (const variant of formats) {
      assert.deepEqual(output.filter((item) => item.variant === variant), input.filter((item) => item.variant === variant));
    }
  }
});
