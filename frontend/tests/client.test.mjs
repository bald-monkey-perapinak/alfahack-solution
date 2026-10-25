import test from 'node:test';
import assert from 'node:assert/strict';
import { AnalyticsApi, ApiError, errorMessage, validationErrors } from '../src/api/client.ts';

const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
test('public endpoints never receive a token; protected endpoints do', async () => {
  const requests = [];
  const api = new AnalyticsApi('https://api.example.test/', async (url, init) => { requests.push({ url, init }); return json({ items: [] }); });
  api.setToken('test-token');
  await api.organizations('металл & логистика', 20); await api.roles(); await api.me();
  assert.match(requests[0].url, /q=%D0%BC/);
  assert.match(requests[0].url, /limit=20&offset=20$/);
  assert.equal(requests[0].init.headers.has('Authorization'), false);
  assert.equal(requests[1].init.headers.has('Authorization'), false);
  assert.equal(requests[2].init.headers.get('Authorization'), 'Bearer test-token');
  assert.equal(requests[2].init.credentials, 'omit');
});
test('default transport invokes native fetch with the correct receiver', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = function () { assert.ok(this === undefined || this === globalThis); return Promise.resolve(json({ status: 'ready' })); };
  try { assert.equal((await new AnalyticsApi('https://api.example.test').health()).status, 'ready'); }
  finally { globalThis.fetch = original; }
});
test('a retried analysis sends exactly the same key and complete selected batch', async () => {
  const requests = [];
  const api = new AnalyticsApi('', async (url, init) => { requests.push({ url, init }); return json({ id: 'job-1', status: 'pending' }, 202); });
  const options = { max_events: 10, material_ids: Array.from({ length: 10 }, (_, index) => index + 1) };
  await api.analyze(options, 'stable-launch'); await api.analyze(options, 'stable-launch');
  for (const request of requests) { assert.equal(request.init.headers.get('Idempotency-Key'), 'stable-launch'); assert.deepEqual(JSON.parse(request.init.body), options); }
  assert.equal(requests.length, 2);
});
test('401 expires a protected session but a bad password does not invoke global logout', async () => {
  const api = new AnalyticsApi('', async () => json({ error: { code: 'invalid_credentials' } }, 401));
  let expired = 0; api.onUnauthorized = () => expired++;
  api.setToken('test-token');
  await assert.rejects(api.login('a@example.test', 'wrong'), { status: 401 }); assert.equal(expired, 0);
  await assert.rejects(api.me(), { status: 401 }); assert.equal(expired, 1);
});
test('an old unauthorized response cannot clear a newly signed-in session', async () => {
  let respond;
  const api = new AnalyticsApi('', () => new Promise((resolve) => { respond = resolve; }));
  let expired = 0; api.onUnauthorized = () => expired++;
  api.setToken('old'); const pending = api.me(); api.setToken('new');
  respond(json({ error: { code: 'invalid_or_expired_token' } }, 401));
  await assert.rejects(pending, { status: 401 }); assert.equal(expired, 0);
});
test('server validation, retry-after and safe request IDs survive error normalization', async () => {
  const api = new AnalyticsApi('', async () => json({ error: { code: 'validation_error', fields: [{ loc: ['body', 'organization_id'], msg: 'invalid', type: 'value_error' }] } }, 422, { 'X-Request-ID': 'safe-id' }));
  await assert.rejects(api.register({}), (error) => { assert.deepEqual(validationErrors(error), { companyId: 'Проверьте значение поля' }); assert.equal(error.requestId, 'safe-id'); return true; });
  const limited = new AnalyticsApi('', async () => json({ error: { code: 'rate_limited' } }, 429, { 'Retry-After': '12' }));
  await assert.rejects(limited.feed(), (error) => { assert.equal(error.retryAfter, 12); assert.match(errorMessage(error), /12 с/u); return true; });
});
test('204 logout clears authorization; pagination and source IDs reach the API', async () => {
  const requests = [];
  const api = new AnalyticsApi('', async (url, init) => { requests.push({ url, init }); return url.endsWith('/logout') ? new Response(null, { status: 204 }) : json({}); });
  api.setToken('token'); await api.materials(12, 6); await api.material(99); await api.feed(6, 6); await api.logout(); await api.me();
  assert.equal(requests[0].url, '/api/v1/materials?kind=news&limit=6&offset=12');
  assert.equal(requests[1].url, '/api/v1/materials/99');
  assert.equal(requests[2].url, '/api/v1/feed?limit=6&offset=6');
  assert.equal(requests[4].init.headers.has('Authorization'), false);
});
test('questions and feedback use real contracts rather than prepared responses', async () => {
  const requests = [];
  const api = new AnalyticsApi('', async (url, init) => { requests.push({ url, init }); return json(url.endsWith('questions') ? { answer: 'server answer', generation_mode: 'live', sources: [{ material_id: 1, quote: 'source text' }] } : { rating: 'already_known', comment: 'Комментарий' }); });
  assert.equal((await api.question(5, 'Почему?')).answer, 'server answer');
  await api.feedback(5, 'already_known', ' Комментарий ');
  assert.equal(requests[0].url, '/api/v1/insights/5/questions');
  assert.deepEqual(JSON.parse(requests[0].init.body), { question: 'Почему?' });
  assert.deepEqual(JSON.parse(requests[1].init.body), { rating: 'already_known', comment: 'Комментарий' });
});
test('transport errors and caller cancellation are distinct; mutation is not repeated automatically', async () => {
  let calls = 0;
  const api = new AnalyticsApi('', async () => { calls++; throw new TypeError('private diagnostic'); });
  await assert.rejects(api.analyze({ max_events: 5 }, 'one'), (error) => error instanceof ApiError && error.code === 'network_error' && !error.message.includes('private'));
  assert.equal(calls, 1);
  const abortable = new AnalyticsApi('', async (_, init) => { if (init.signal.aborted) throw new DOMException('Aborted', 'AbortError'); return json({}); });
  const controller = new AbortController(); controller.abort();
  await assert.rejects(abortable.me(controller.signal), { name: 'AbortError' });
});
