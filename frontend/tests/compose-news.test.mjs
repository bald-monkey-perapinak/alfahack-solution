import assert from 'node:assert/strict';
import test from 'node:test';
import {
  composeNewsContainers,
  getNewsImportanceStats,
  DEFAULT_NEWS_LAYOUT_POLICY,
} from '../src/lib/news-layout/composeNewsContainers.ts';

function makeNews(scores) {
  return scores.map((importance, index) => ({
    id: `news-${String(index).padStart(4, '0')}`,
    title: `Новость ${index}`,
    importance,
    summary: '',
    source: { name: 'Пример', url: 'https://example.com/' },
    publishedAt: '2026-10-22T10:00:00+03:00',
    topic: 'Макроэкономика',
    urgency: 'normal',
    isFavorite: false,
    analysisStatus: 'ready',
  }));
}

const flatten = (containers) => containers.flatMap(({ items }) => items);
const shape = (containers) => containers.map(({ variant, placement, items }) => ({
  variant, placement, scores: items.map(({ importance }) => importance),
}));

test('пустая группа возвращает пустой массив и статистику без вымышленных значений', () => {
  assert.deepEqual(composeNewsContainers([]), []);
  assert.deepEqual(getNewsImportanceStats([]), {
    count: 0, mean: null, median: null, exceptional: 0, high: 0, medium: 0, low: 0,
  });
});

test('пример 15 новостей: highlights, два Hero, Duo, два Trio, Quartet', () => {
  const scores = [98, 93, 88, 77, 71, 49, 38, 35, 32, 22, 19, 16, 12, 8, 4];
  const result = composeNewsContainers(makeNews(scores), { groupId: 'economy', groupTitle: 'Экономика' });
  assert.deepEqual(shape(result), [
    { variant: 'hero', placement: 'highlights', scores: [98] },
    { variant: 'hero', placement: 'group', scores: [93] },
    { variant: 'hero', placement: 'group', scores: [88] },
    { variant: 'duo', placement: 'group', scores: [77, 71] },
    { variant: 'trio', placement: 'group', scores: [49, 38, 35] },
    { variant: 'trio', placement: 'group', scores: [32, 22, 19] },
    { variant: 'quartet', placement: 'group', scores: [16, 12, 8, 4] },
  ]);
  assert.equal(result[0].title, 'Самое главное');
  assert.ok(result.slice(1).every(({ title }) => title === 'Экономика'));
  assert.deepEqual(flatten(result).map(({ importance }) => importance), scores);
  assert.deepEqual(getNewsImportanceStats(makeNews(scores)), {
    count: 15, mean: 662 / 15, median: 35, exceptional: 1, high: 2, medium: 2, low: 10,
  });
});

test('чётная медиана и непересекающиеся категории на границах порогов', () => {
  assert.deepEqual(getNewsImportanceStats(makeNews([0, 49, 50, 79, 80, 94, 95, 100])), {
    count: 8, mean: 547 / 8, median: 79.5, exceptional: 2, high: 2, medium: 2, low: 2,
  });
});

test('сортирует копию по важности, новой дате, затем id; сохраняет исходные объекты', () => {
  const items = makeNews([10, 70, 70, 70]);
  items[1].publishedAt = '2026-10-21T10:00:00+03:00';
  const before = structuredClone(items);
  const references = new Map(items.map((item) => [item.id, item]));
  for (const item of items) Object.freeze(item);
  Object.freeze(items);
  const result = flatten(composeNewsContainers(items));
  assert.deepEqual(result.map(({ id }) => id), ['news-0002', 'news-0003', 'news-0001', 'news-0000']);
  assert.deepEqual(items, before);
  for (const item of result) assert.equal(item, references.get(item.id));
});

test('все низкие оценки не получают акцентные Hero', () => {
  const result = composeNewsContainers(makeNews([49, 45, 43, 40, 35, 30, 24, 20, 14, 10, 5, 3, 2, 1, 0]));
  assert.ok(result.every(({ variant }) => variant !== 'hero'));
  assert.ok(result.every(({ variant }) => variant === 'trio' || variant === 'quartet'));
});

test('медиана не позволяет объявить обычный материал главным в равномерно важной группе', () => {
  const result = composeNewsContainers(makeNews(Array(15).fill(85)));
  assert.ok(result.every(({ variant }) => variant !== 'hero'));
});

test('особо важные материалы расходуют общий бюджет Hero', () => {
  const result = composeNewsContainers(makeNews([100, 99, 98, 97, 96, 94, 93, 90, 85, 70, 60, 40, 30, 20, 10]));
  assert.equal(result.filter(({ variant }) => variant === 'hero').length, 3);
  assert.equal(result.filter(({ placement }) => placement === 'highlights').length, 3);
  assert.equal(flatten(result).length, 15);
});

test('сопоставимые средние новости образуют Duo; у Trio первым идёт лидер', () => {
  assert.deepEqual(shape(composeNewsContainers(makeNews([77, 71, 49, 38, 35]))), [
    { variant: 'duo', placement: 'group', scores: [77, 71] },
    { variant: 'trio', placement: 'group', scores: [49, 38, 35] },
  ]);
  const dominant = composeNewsContainers(makeNews([49, 35, 33, 30, 28, 25, 20]));
  assert.equal(dominant[0].reason, 'dominant-lead');
  assert.equal(dominant[0].variant, 'trio');
});

test('низкие остатки: 5 = 2+3, 6 = 3+3, 7 = 4+3, 8 = 4+4, 9 = 3+3+3', () => {
  for (const [count, sizes] of [[5, [2, 3]], [6, [3, 3]], [7, [4, 3]], [8, [4, 4]], [9, [3, 3, 3]]]) {
    const result = composeNewsContainers(makeNews(Array(count).fill(20)));
    assert.deepEqual(result.map(({ items }) => items.length), sizes, `count=${count}`);
  }
});

test('маленькие группы и единственная новость имеют явные исключения', () => {
  assert.equal(composeNewsContainers(makeNews([10]))[0].reason, 'single-item');
  assert.equal(composeNewsContainers(makeNews([98]))[0].placement, 'highlights');
  assert.deepEqual(composeNewsContainers(makeNews([98, 10])).map(({ variant }) => variant), ['duo']);
  assert.deepEqual(shape(composeNewsContainers(makeNews([98, 30, 20]))), [
    { variant: 'hero', placement: 'highlights', scores: [98] },
    { variant: 'duo', placement: 'group', scores: [30, 20] },
  ]);
});

test('сокращает Hero-отбор, если он оставляет одну обычную новость', () => {
  const result = composeNewsContainers(makeNews([99, 98, 97, 96, 95, 94]), {
    policy: { heroRatio: 1, maxHeroCount: 5, maxHighlights: 5 },
  });
  assert.deepEqual(result.map(({ items }) => items.length), [1, 1, 1, 1, 2]);
});

test('пороги настраиваются; отключение Hero/подборки не теряет новости', () => {
  const result = composeNewsContainers(makeNews([100, 95, 90, 85, 80]), {
    policy: { heroRatio: 0, maxHighlights: 0 },
  });
  assert.ok(result.every(({ variant }) => variant !== 'hero'));
  assert.equal(flatten(result).length, 5);
  assert.equal(composeNewsContainers(makeNews([98, 30, 20]), {
    policy: { maxHeroCount: 0 },
  }).length, 1);
  const stats = getNewsImportanceStats(makeNews([70, 50, 20]), {
    mediumThreshold: 30, heroThreshold: 60, highlightThreshold: 90,
  });
  assert.equal(stats.high, 1);
  assert.equal(stats.medium, 1);
  assert.equal(stats.low, 1);
});

test('достоверность не подменяет importance', () => {
  const items = makeNews([70, 60, 40, 30, 20, 10]);
  const expected = shape(composeNewsContainers(items));
  items[5].confidence = { value: 5, scale: 5, isDemo: true };
  assert.deepEqual(shape(composeNewsContainers(items)), expected);
});

test('срочная группа соблюдает лимиты Hero и использует Duo/Trio', () => {
  const items = makeNews([10, 98, 35, 0, 60]);
  items.forEach((item) => { item.urgency = 'urgent'; });
  const result = composeNewsContainers(items, {
    policy: { heroRatio: 0, maxHeroCount: 0, maxHighlights: 0 },
  });
  assert.deepEqual(shape(result), [
    { variant: 'duo', placement: 'urgent', scores: [98, 60] },
    { variant: 'trio', placement: 'urgent', scores: [35, 10, 0] },
  ]);
  assert.ok(result.every(({ title }) => title === 'Срочные новости'));
  assert.deepEqual(flatten(result).map(({ importance }) => importance), [98, 60, 35, 10, 0]);
});

test('срочная новость идёт в urgent, даже если подходит для «Самого главного»', () => {
  const items = makeNews([99, 98, 40, 30, 20, 10]);
  items[0].urgency = 'urgent';
  const result = composeNewsContainers(items);
  assert.deepEqual(shape(result), [
    { variant: 'hero', placement: 'urgent', scores: [99] },
    { variant: 'hero', placement: 'highlights', scores: [98] },
    { variant: 'quartet', placement: 'group', scores: [40, 30, 20, 10] },
  ]);
  assert.equal(new Set(flatten(result).map(({ id }) => id)).size, items.length);
});

test('выделение срочных не меняет медиану и квоту несрочной части', () => {
  const regular = makeNews([93, 88, 77, 71, 49, 38, 35, 32, 22, 19, 16, 12, 8, 4, 0]);
  const urgent = makeNews(Array(30).fill(100)).map((item) => ({
    ...item, id: `urgent-${item.id}`, urgency: 'urgent',
  }));
  const expected = composeNewsContainers(regular);
  const result = composeNewsContainers([...regular, ...urgent]);
  assert.deepEqual(result.filter(({ placement }) => placement !== 'urgent'), expected);
  const urgentContainers = result.filter(({ placement }) => placement === 'urgent');
  assert.equal(flatten(urgentContainers).length, 30);
  assert.equal(urgentContainers.filter(({ variant }) => variant === 'hero').length, 3);
});

test('15 срочных компонуются как обычные, но все контейнеры остаются в urgent', () => {
  const items = makeNews([98, 93, 88, 77, 71, 49, 38, 35, 32, 22, 19, 16, 12, 8, 4]);
  const expected = composeNewsContainers(items).map((container) => ({
    ...container,
    placement: 'urgent',
    reason: container.reason === 'highlight' ? 'important' : container.reason,
  }));
  items.forEach((item) => { item.urgency = 'urgent'; });
  const result = composeNewsContainers(items);
  assert.deepEqual(shape(result), shape(expected));
  assert.deepEqual(result.map(({ reason }) => reason), expected.map(({ reason }) => reason));
  assert.deepEqual(result.map(({ variant }) => variant), ['hero', 'hero', 'hero', 'duo', 'trio', 'trio', 'quartet']);
  assert.ok(result.every(({ placement, reason }) => placement === 'urgent' && reason !== 'highlight'));
});

test('срочные с оценкой 95+ остаются внутри своей группы, maxHighlights на них не влияет', () => {
  const items = makeNews([99, 98, 97, 70, 65, 40, 30, 20, 10, 0]);
  items.forEach((item) => { item.urgency = 'urgent'; });
  const expected = composeNewsContainers(items);
  const result = composeNewsContainers(items, { policy: { maxHighlights: 0 } });
  assert.deepEqual(result, expected);
  assert.equal(result.filter(({ variant }) => variant === 'hero').length, 2);
  assert.ok(result.every(({ placement }) => placement === 'urgent'));
});

test('маленькие срочные группы используют те же правила остатка и exceptional Hero', () => {
  for (const [scores, variants] of [
    [[98, 10], ['duo']],
    [[98, 30, 20], ['hero', 'duo']],
    [[40, 30, 20], ['trio']],
    [[40, 35, 30, 20], ['quartet']],
  ]) {
    const items = makeNews(scores).map((item) => ({ ...item, urgency: 'urgent' }));
    const result = composeNewsContainers(items);
    assert.deepEqual(result.map(({ variant }) => variant), variants);
    assert.ok(result.every(({ placement }) => placement === 'urgent'));
  }
});

test('низкие срочные группы упаковываются в Trio/Quartet, не превращаясь в Hero', () => {
  for (let count = 6; count <= 100; count++) {
    const items = makeNews(Array.from({ length: count }, (_, i) => (i * 17) % 50))
      .map((item) => ({ ...item, urgency: 'urgent' }));
    const result = composeNewsContainers(items);
    assert.ok(result.every(({ placement, variant }) => placement === 'urgent'
      && (variant === 'trio' || variant === 'quartet')));
    assert.equal(flatten(result).length, count);
  }
});

test('сначала срочные, затем highlights и обычные; сортировка по важности внутри разделов', () => {
  const items = makeNews([98, 10, 77, 71, 40, 30, 20]);
  items[1].urgency = 'urgent';
  const result = composeNewsContainers(items);
  assert.deepEqual(result.map(({ placement }) => placement), ['urgent', 'highlights', 'group', 'group']);
  assert.deepEqual(flatten(result).map(({ importance }) => importance), [10, 98, 77, 71, 40, 30, 20]);
  assert.equal(flatten(result).length, items.length);
});

test('планируемые новости не относятся к срочным', () => {
  const items = makeNews([70, 60, 40, 30, 20, 10]);
  const expected = shape(composeNewsContainers(items));
  items.forEach((item) => { item.urgency = 'planned'; });
  const result = composeNewsContainers(items);
  assert.deepEqual(shape(result), expected);
  assert.ok(result.every(({ placement }) => placement !== 'urgent'));
});

test('при смешанной срочности сохраняются все новости, квота и порядок разделов', () => {
  const ranks = { urgent: 0, highlights: 1, group: 2 };
  for (let count = 1; count <= 100; count++) {
    const items = makeNews(Array.from({ length: count }, (_, i) => (i * 37 + count) % 101));
    items.forEach((item, i) => { if (i % 3 === 0) item.urgency = 'urgent'; });
    const snapshot = structuredClone(items);
    const result = composeNewsContainers(items);
    const output = flatten(result);
    assert.equal(output.length, count);
    assert.equal(new Set(output.map(({ id }) => id)).size, count);
    assert.deepEqual(items, snapshot);
    assert.ok(result.every((container, index) => index === 0
      || ranks[result[index - 1].placement] <= ranks[container.placement]));
    for (const placement of ['urgent', 'highlights', 'group']) {
      const scores = flatten(result.filter((item) => item.placement === placement)).map(({ importance }) => importance);
      assert.deepEqual(scores, [...scores].sort((a, b) => b - a));
    }
    for (const container of result) {
      assert.ok(container.items.every(({ urgency }) => (urgency === 'urgent') === (container.placement === 'urgent')));
    }
    for (const urgentPart of [true, false]) {
      const section = items.filter(({ urgency }) => (urgency === 'urgent') === urgentPart);
      const actual = result.filter(({ placement }) => (placement === 'urgent') === urgentPart);
      assert.deepEqual(actual, composeNewsContainers(section));
      if (section.length >= 5) {
        assert.ok(actual.filter(({ variant }) => variant === 'hero').length
          <= Math.min(3, Math.floor(section.length * 0.2)));
      }
    }
  }
});

test('идентификаторы стабильны и различаются между исходными группами', () => {
  const items = makeNews([70, 60, 40, 30, 20, 10]);
  const ids = (options) => composeNewsContainers(items, options).map(({ id }) => id);
  assert.deepEqual(ids({ groupId: 'a' }), ids({ groupId: 'a' }));
  assert.ok(ids({ groupId: 'a' }).every((id) => !ids({ groupId: 'b' }).includes(id)));
});

test('отклоняет повторные id, неверные оценки, даты и настройки', () => {
  const duplicate = makeNews([10, 20]);
  duplicate[1].id = duplicate[0].id;
  assert.throws(() => composeNewsContainers(duplicate), /Повторяющийся id/);
  for (const importance of [-1, 101, NaN, Infinity, undefined, '90']) {
    assert.throws(() => composeNewsContainers([{ ...makeNews([10])[0], importance }]), /Важность/);
  }
  assert.throws(() => composeNewsContainers([{ ...makeNews([10])[0], publishedAt: 'bad-date' }]), /дата/);
  assert.throws(() => composeNewsContainers([{ ...makeNews([10])[0], id: '' }]), /id/);
  for (const policy of [
    { heroRatio: -1 }, { heroRatio: 1.1 }, { maxHeroCount: 1.5 },
    { maxHighlights: -1 }, { trioMinGap: NaN }, { duoMaxGap: 101 },
    { mediumThreshold: 90, heroThreshold: 80 },
  ]) assert.throws(() => composeNewsContainers([], { policy }));
  assert.throws(() => composeNewsContainers([], { groupId: '' }), /groupId/);
});

test('инварианты на 1010 группах: сохранность, порядок, размеры, лимиты и отсутствие одиночного хвоста', () => {
  let seed = 12345;
  const nextScore = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed % 101;
  };
  const expectedSizes = { hero: 1, duo: 2, trio: 3, quartet: 4 };
  for (let count = 0; count <= 100; count++) {
    for (let run = 0; run < 10; run++) {
      const input = makeNews(Array.from({ length: count }, nextScore));
      const result = composeNewsContainers(input);
      const output = flatten(result);
      assert.equal(output.length, input.length);
      assert.equal(new Set(output.map(({ id }) => id)).size, input.length);
      assert.deepEqual(output.map(({ importance }) => importance), input.map(({ importance }) => importance).sort((a, b) => b - a));
      assert.equal(new Set(result.map(({ id }) => id)).size, result.length);
      for (const container of result) {
        assert.equal(container.items.length, expectedSizes[container.variant]);
        if (container.variant === 'hero' && count > 1) {
          assert.ok(container.reason === 'highlight' || container.reason === 'important');
        }
      }
      if (count >= 5) {
        assert.ok(result.filter(({ variant }) => variant === 'hero').length
          <= Math.min(DEFAULT_NEWS_LAYOUT_POLICY.maxHeroCount, Math.floor(count * 0.2)));
      }
    }
  }
});

test('низкие группы от 6 до 150 материалов обходятся только Trio и Quartet', () => {
  for (let count = 6; count <= 150; count++) {
    const result = composeNewsContainers(makeNews(Array.from({ length: count }, (_, i) => (i * 17) % 50)));
    assert.ok(result.every(({ variant }) => variant === 'trio' || variant === 'quartet'), `count=${count}`);
    assert.equal(flatten(result).length, count);
  }
});
