import assert from 'node:assert/strict';
import test from 'node:test';
import { buildNewsFeed } from '../src/lib/news-layout/buildNewsFeed.ts';
import { demoNews } from '../src/mocks/news.ts';
import { topics } from '../src/types/news.ts';

const flatten = (sections) => sections.flatMap(({ containers }) => containers.flatMap(({ items }) => items));

function makeNews(id, importance, topic = topics[0], urgency = 'normal') {
  return {
    id, importance, topic, urgency,
    title: id, summary: 'Пример',
    source: { name: 'Источник', url: 'https://example.com/' },
    publishedAt: '2026-10-22T10:00:00+03:00',
    isFavorite: false, analysisStatus: 'ready',
  };
}

test('пустая лента не создаёт пустых разделов', () => {
  assert.deepEqual(buildNewsFeed([]), []);
});

test('демо: все 26 новостей показаны один раз, тема назначается данными', () => {
  const sections = buildNewsFeed(demoNews);
  const output = flatten(sections);
  assert.equal(output.length, 26);
  assert.equal(new Set(output.map(({ id }) => id)).size, demoNews.length);
  assert.ok(output.every((item) => demoNews.includes(item)));
  assert.deepEqual(sections.map(({ id }) => id), [
    'urgent', 'highlights', 'topic:Макроэкономика', 'topic:Финансы и Банки',
    'topic:Налоги и Право', 'topic:Логистика и ВЭД',
  ]);
  for (const section of sections) {
    const items = flatten([section]);
    assert.equal(section.count, items.length);
    assert.ok(items.length > 0);
    if (section.topic) assert.ok(items.every((item) => item.topic === section.topic));
  }
});

test('несколько контейнеров одной темы проходят обе стадии и получают одну секцию', () => {
  const sections = buildNewsFeed(demoNews);
  const finance = sections.filter(({ topic }) => topic === 'Финансы и Банки');
  assert.equal(finance.length, 1);
  assert.equal(finance[0].count, 14);
  assert.deepEqual(finance[0].containers.map(({ variant }) => variant), ['hero', 'duo', 'hero', 'trio', 'quartet', 'trio']);
  const raw = buildNewsFeed(demoNews, { arrangement: { maxShift: 0 } })
    .find(({ topic }) => topic === 'Финансы и Банки');
  assert.deepEqual(raw.containers.map(({ variant }) => variant), ['hero', 'hero', 'duo', 'trio', 'trio', 'quartet']);
  assert.deepEqual(finance[0].containers.map(({ id }) => id).sort(), raw.containers.map(({ id }) => id).sort());
});

test('срочные из разных тем объединяются и никогда не попадают в highlights', () => {
  const sections = buildNewsFeed(demoNews);
  const urgent = sections.find(({ placement }) => placement === 'urgent');
  assert.equal(urgent.count, 5);
  assert.deepEqual(urgent.containers.map(({ variant }) => variant), ['hero', 'quartet']);
  assert.ok(new Set(flatten([urgent]).map(({ topic }) => topic)).size > 1);
  assert.ok(urgent.containers.every(({ sourceGroupId }) => sourceGroupId === 'feed-urgent'));
  for (const section of sections) {
    assert.ok(flatten([section]).every(({ urgency }) => (urgency === 'urgent') === (section.placement === 'urgent')));
  }
});

test('общий лимит highlights между темами; лишние кандидаты остаются Hero своих тем', () => {
  const news = topics.slice(0, 4).flatMap((topic, i) => [99 - i, 40, 30, 20, 10]
    .map((importance, j) => makeNews(`${i}-${j}`, importance, topic)));
  const sections = buildNewsFeed(news);
  const highlights = sections.find(({ placement }) => placement === 'highlights');
  assert.deepEqual(flatten([highlights]).map(({ importance }) => importance), [99, 98, 97]);
  const overflow = sections.find(({ topic }) => topic === topics[3]);
  assert.equal(overflow.count, 5);
  assert.equal(overflow.containers[0].variant, 'hero');
  assert.equal(overflow.containers[0].placement, 'group');
  assert.equal(overflow.containers[0].reason, 'important');
  assert.equal(overflow.containers[0].items[0].importance, 96);
  const output = flatten(sections);
  assert.equal(output.length, news.length);
  assert.equal(new Set(output.map(({ id }) => id)).size, news.length);
  assert.equal(new Set(sections.flatMap(({ containers }) => containers.map(({ id }) => id))).size,
    sections.reduce((sum, section) => sum + section.containers.length, 0));
});

test('фильтр темы работает и для срочных, и для «Самого главного»', () => {
  const selected = demoNews.filter(({ topic }) => topic === 'Финансы и Банки');
  const sections = buildNewsFeed(selected);
  assert.ok(flatten(sections).every(({ topic }) => topic === 'Финансы и Банки'));
  assert.equal(flatten(sections).length, selected.length);
  assert.deepEqual(sections.map(({ placement }) => placement), ['urgent', 'highlights', 'group']);
});

test('только срочные и избранное не теряют материалы при повторной компоновке', () => {
  const urgent = demoNews.filter(({ urgency }) => urgency === 'urgent');
  const urgentSections = buildNewsFeed(urgent);
  assert.equal(urgentSections.length, 1);
  assert.equal(urgentSections[0].placement, 'urgent');
  assert.equal(urgentSections[0].count, urgent.length);
  const favorites = demoNews.filter(({ isFavorite }) => isFavorite);
  const sections = buildNewsFeed(favorites);
  assert.equal(flatten(sections).length, favorites.length);
  assert.ok(flatten(sections).every(({ isFavorite }) => isFavorite));
});

test('добавление срочных не меняет содержимое и квоты тематических разделов', () => {
  const regular = demoNews.filter(({ urgency }) => urgency !== 'urgent');
  const expected = buildNewsFeed(regular);
  const actual = buildNewsFeed(demoNews).filter(({ placement }) => placement !== 'urgent');
  assert.deepEqual(actual, expected);
});

test('отключение highlights не удаляет новости и не отключает срочный раздел', () => {
  const sections = buildNewsFeed(demoNews, { policy: { maxHighlights: 0 } });
  assert.ok(sections.every(({ placement }) => placement !== 'highlights'));
  assert.equal(sections[0].placement, 'urgent');
  assert.equal(flatten(sections).length, demoNews.length);
});

test('не мутирует вход; повторные id между темами и неизвестные темы отклоняются', () => {
  const news = [makeNews('a', 70), makeNews('b', 60, topics[1])];
  const before = structuredClone(news);
  news.forEach(Object.freeze);
  Object.freeze(news);
  buildNewsFeed(news);
  assert.deepEqual(news, before);
  assert.throws(() => buildNewsFeed([makeNews('a', 70), makeNews('a', 60, topics[1])]), /Повторяющийся id/);
  assert.throws(() => buildNewsFeed([{ ...makeNews('a', 70), topic: 'Неизвестная тема' }]), /Неизвестная тема/);
  assert.throws(() => buildNewsFeed([], { policy: { heroRatio: -1 } }), /heroRatio/);
  assert.throws(() => buildNewsFeed([], { arrangement: { maxShift: -1 } }), /maxShift/);
});
