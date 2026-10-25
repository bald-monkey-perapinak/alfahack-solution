import test from 'node:test';
import assert from 'node:assert/strict';
import { getAppRoute, routeTitles } from '../src/lib/navigation.ts';

test('пункты боковой навигации и профиль имеют независимые маршруты', () => {
  assert.equal(getAppRoute('#/'), 'feed');
  assert.equal(getAppRoute('#/favorites'), 'favorites');
  assert.equal(getAppRoute('#/analysis'), 'analysis');
  assert.equal(getAppRoute('#/profile'), 'profile');
  assert.equal(getAppRoute('#/login'), 'login');
  assert.equal(getAppRoute('#/register'), 'register');
});

test('прямые ссылки на новости и пустой hash открывают ленту', () => {
  for (const hash of ['', '#news-key-rate', '#news-liquidity', '#/unknown']) assert.equal(getAppRoute(hash), 'feed');
});

test('у каждого раздела собственный заголовок вкладки', () => {
  assert.equal(new Set(Object.values(routeTitles)).size, 6);
  assert.match(routeTitles.favorites, /^Избранное/);
  assert.match(routeTitles.analysis, /^Анализ/);
});
