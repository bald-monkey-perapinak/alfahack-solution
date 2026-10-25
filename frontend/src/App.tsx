import { useEffect, useRef, useState } from 'react';
import { BarChartMIcon } from '@alfalab/icons-glyph/BarChartMIcon';
import { DocumentLinesMIcon } from '@alfalab/icons-glyph/DocumentLinesMIcon';
import { Badge, Button, Callout, Circle, Modal, Select, Spinner, Text } from './components/ui';
import { InlineError } from './components/ApiFeedback';
import { SourceModal, type SourceTarget } from './components/SourceModal';
import { AnalyticsApi, isAborted } from './api/client';
import type { AnalysisOptions, User } from './api/types';
import { initials, parseRoute, publicationLabel, roleLabel, type Role, type Route } from './domain';
import { useResource } from './hooks/useResource';
import { useAnalysisJob } from './hooks/useAnalysisJob';
import { EntryPage, type EntryValues } from './pages/EntryPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { DetailPage } from './pages/DetailPage';
import { NewsPage } from './pages/NewsPage';
import { ProfilePage } from './pages/ProfilePage';

function navigate(path: string) { window.location.hash = `/${path}`; }
export default function App() {
  const [api] = useState(() => new AnalyticsApi(import.meta.env.VITE_API_BASE_URL || ''));
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const [session, setSession] = useState<{ user: User; expiresAt: string } | null>(null);
  const [sessionNotice, setSessionNotice] = useState('');
  const [information, setInformation] = useState('');
  useEffect(() => {
    function change() { setRoute(parseRoute(window.location.hash)); window.scrollTo(0, 0); }
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  useEffect(() => {
    api.onUnauthorized = () => { setSession(null); setSessionNotice('Сессия завершена. Войдите повторно, чтобы продолжить работу.'); };
    return () => { api.onUnauthorized = undefined; };
  }, [api]);
  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(() => {
      api.setToken(null); setSession(null); setSessionNotice('Срок действия сессии истёк. Войдите повторно.');
    }, Math.max(0, Date.parse(session.expiresAt) - Date.now()));
    return () => clearTimeout(timer);
  }, [api, session]);
  useEffect(() => {
    const title = !session ? route.page === 'register' ? 'Регистрация' : 'Вход' : route.page === 'news' ? 'Новости' : route.page === 'profile' ? 'Профиль' : route.page === 'detail' ? 'Подробный анализ' : 'Моя аналитика';
    document.title = `${title} — Альфа-Бизнес`;
  }, [route, session]);
  async function enter(values: EntryValues, register: boolean, signal: AbortSignal) {
    const result = register
      ? await api.register({ name: values.name.trim(), email: values.email.trim(), password: values.password, role: values.role as Role, organization_id: Number(values.companyId) }, signal)
      : await api.login(values.email.trim(), values.password, signal);
    if (signal.aborted) return;
    api.setToken(result.access_token);
    try {
      const user = result.user || await api.me(signal);
      if (signal.aborted) { api.setToken(null); return; }
      setSession({ user, expiresAt: result.expires_at }); setSessionNotice(''); window.scrollTo(0, 0);
      if (['login', 'register'].includes(route.page)) navigate('analysis');
    } catch (cause) { api.setToken(null); throw cause; }
  }
  return <>
    <a href="#main-content" className="skip-link" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>К содержимому</a>
    {session ? <AuthenticatedApp key={session.user.id} api={api} route={route} user={session.user} updateUser={(user) => setSession((current) => current ? { ...current, user } : null)} onLogout={() => { api.setToken(null); setSession(null); navigate('login'); }} /> : <div id="main-content" tabIndex={-1}><EntryPage key={route.page === 'register' ? 'register' : 'login'} api={api} register={route.page === 'register'} onEnter={enter} info={setInformation} sessionNotice={sessionNotice} /></div>}
    <Modal open={Boolean(information)} onClose={() => setInformation('')} size={500} hasCloser><Modal.Header title="Возможность в разработке" /><Modal.Content><Text>{information}</Text></Modal.Content><Modal.Footer><Button view="primary" size={40} className="dark-button" onClick={() => setInformation('')}>Понятно</Button></Modal.Footer></Modal>
  </>;
}

function AuthenticatedApp({ api, route, user, updateUser, onLogout }: { api: AnalyticsApi; route: Route; user: User; updateUser: (user: User) => void; onLogout: () => void }) {
  const [feedRevision, setFeedRevision] = useState(0);
  const company = useResource((signal) => api.organization(signal), [api, user.org_id]);
  const health = useResource((signal) => api.health(signal), [api]);
  const monitor = useAnalysisJob(api, user.id, () => setFeedRevision((value) => value + 1));
  const [launchOpen, setLaunchOpen] = useState(false);
  const [batch, setBatch] = useState<number[] | undefined>();
  const [count, setCount] = useState(5);
  const [launchBusy, setLaunchBusy] = useState(false);
  const [launchError, setLaunchError] = useState<unknown>(null);
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);
  const launchRequest = useRef<AbortController | null>(null);
  const launchKey = useRef<{ signature: string; key: string } | null>(null);
  useEffect(() => () => launchRequest.current?.abort(), []);
  useEffect(() => { setSource(null); }, [route.page, route.id]);
  const org = company.data?.organization;
  const companyName = org?.name || org?.synthetic_u || `Компания #${user.org_id}`;
  const context = `${companyName} · ${roleLabel(user.role)}`;
  const analysisBusy = monitor.active || monitor.restoring || launchBusy;
  const analysisPage = !['news', 'profile', 'detail'].includes(route.page);
  function prepare(ids?: number[]) {
    if (analysisBusy) return;
    setBatch(ids); setCount(ids?.length || 5); setLaunchError(null); launchKey.current = null; setLaunchOpen(true);
  }
  async function startJob() {
    if (launchBusy || monitor.active) return;
    const options: AnalysisOptions = { max_events: batch?.length || count, ...(batch ? { material_ids: batch } : {}) };
    const signature = JSON.stringify(options);
    if (launchKey.current?.signature !== signature) launchKey.current = { signature, key: crypto.randomUUID() };
    const controller = new AbortController(); launchRequest.current = controller;
    setLaunchBusy(true); setLaunchError(null);
    try {
      const next = await api.analyze(options, launchKey.current.key, controller.signal);
      if (!controller.signal.aborted) { monitor.watch(next); setLaunchOpen(false); navigate('analysis'); }
    } catch (cause) { if (!controller.signal.aborted && !isAborted(cause)) setLaunchError(cause); }
    finally { if (!controller.signal.aborted) setLaunchBusy(false); }
  }
  async function logout() {
    if (logoutBusy) return;
    setLogoutBusy(true); setLogoutError(null);
    try { await api.logout(); monitor.clear(); onLogout(); }
    catch (cause) { setLogoutError(cause); setLogoutBusy(false); }
  }
  function savedUser(next: User) {
    if (next.role !== user.role) { monitor.clear(); setFeedRevision((value) => value + 1); }
    updateUser(next);
  }
  const parts = user.name.trim().split(/\s+/u);
  const shortName = `${parts[0]}${parts[1] ? ` ${parts[1][0]}.` : ''}`;
  return <div className="app-shell">
    <header className="app-header"><a className="brand" href="#/analysis"><span className="brand-tile">А</span><span>Альфа-Бизнес<small>Новости и аналитика</small></span></a><Button view="text" size={48} href="#/profile" className="profile-link"><Circle size={40} backgroundColor="#F3F4F6" text={initials(user.name)} /><span className="profile-link-label"><strong>{shortName}</strong><span>Профиль</span></span></Button></header>
    <div className="app-body"><aside className="sidebar"><nav aria-label="Основная навигация"><Button href="#/analysis" view="text" size={48} className={`nav-item ${analysisPage || route.page === 'detail' ? 'active' : ''}`} aria-current={analysisPage || route.page === 'detail' ? 'page' : undefined} leftAddons={<BarChartMIcon />}>Анализ</Button><Button href="#/news" view="text" size={48} className={`nav-item ${route.page === 'news' ? 'active' : ''}`} aria-current={route.page === 'news' ? 'page' : undefined} leftAddons={<DocumentLinesMIcon />}>Новости</Button></nav><div className="sidebar-note"><span className="demo-dot" /><span>Персональная аналитика<br />Для вашей компании</span></div></aside>
      <main id="main-content" className="workspace" tabIndex={-1}><div className="content"><div className="prototype-notice service-notice"><span>{health.loading ? <><Spinner visible preset={16} />Проверяем состояние сервиса…</> : health.error ? 'Состояние сервиса не подтверждено' : <><span className="service-dot" />Сервис доступен · {health.data?.generation_mode === 'live' ? 'Анализ с LLM' : 'Анализ по правилам, без LLM'}</>}</span><Button view="text" size={32} disabled={health.loading} onClick={health.reload}>Обновить статус</Button></div>
        {Boolean(health.error) && <div className="page-notice"><InlineError error={health.error} retry={health.reload} /></div>}
        {Boolean(company.error) && route.page !== 'profile' && <div className="page-notice"><InlineError error={company.error} retry={company.reload} /></div>}
        {monitor.active && !analysisPage && <div className="page-notice"><Callout>Аналитика готовится. Вы можете продолжить работу. <Button view="text" size={32} href="#/analysis">Перейти к заданию →</Button></Callout></div>}
        {route.page === 'news' ? <NewsPage api={api} analyze={prepare} source={(id) => setSource({ id })} analysisBusy={analysisBusy} />
          : route.page === 'profile' ? <ProfilePage api={api} user={user} company={company.data} companyLoading={company.loading} companyError={company.error} reloadCompany={company.reload} savedUser={savedUser} logout={() => void logout()} logoutBusy={logoutBusy} logoutError={logoutError} />
          : route.page === 'detail' ? <DetailPage key={route.id} api={api} id={route.id || ''} companyName={companyName} serverMode={health.data?.generation_mode} source={setSource} />
          : <AnalyticsPage api={api} revision={feedRevision} job={monitor.job} jobError={monitor.error} restoring={monitor.restoring} retryJob={monitor.retry} clearJob={monitor.clear} context={context} prepare={() => prepare()} onSourceChoice={() => navigate('news')} />}
        <footer className="workspace-footer"><span>Альфа-Бизнес · Новости и аналитика</span><span>Источники и ограничения — в каждом анализе</span></footer>
      </div></main></div>
    <Modal open={launchOpen} onClose={() => { if (!launchBusy) setLaunchOpen(false); }} size={600} hasCloser className="launch-modal">
      <Modal.Header title="Подготовить аналитику" /><Modal.Content><div className="stack">
        <div className="subcard"><span className="caption">Анализ для компании</span><strong>{companyName}</strong><Text>{roleLabel(user.role)}</Text></div>
        {batch ? <><Badge>Выбрано: {batch.length} {publicationLabel(batch.length)}</Badge><Text>Будут обработаны выбранные материалы. Изменить выбор можно в разделе «Новости».</Text></> : <Select size={48} block labelView="outer" label="Количество публикаций для обработки" selected={String(count)} disabled={launchBusy} options={Array.from({ length: 10 }, (_, index) => ({ key: String(index + 1), content: `${index + 1} ${publicationLabel(index + 1)}` }))} fieldProps={{ fieldClassName: 'control-surface' }} onChange={({ selected }) => setCount(Number(selected?.key || 5))} />}
        <Text>Будут обработаны {batch ? 'выбранные новости' : 'последние подготовленные новости по дате публикации'} с учётом профиля компании и вашей роли.</Text>
        <Callout>Часть публикаций может быть пропущена, если данных для персонального вывода недостаточно.</Callout>
        {health.data?.generation_mode === 'offline' && <Text className="caption">Сейчас сервис работает по правилам, без вызова LLM.</Text>}
        {Boolean(launchError) && <><InlineError error={launchError} /><Text className="caption">Повтор с теми же параметрами использует тот же ключ запуска и не создаёт дубликат задания.</Text></>}
      </div></Modal.Content><Modal.Footer><div className="modal-actions"><Button view="secondary" size={40} disabled={launchBusy} onClick={() => setLaunchOpen(false)}>Отмена</Button><Button view="accent" size={40} className="accent-button" disabled={launchBusy} loading={launchBusy} onClick={() => void startJob()}>Запустить анализ</Button></div></Modal.Footer>
    </Modal>
    {source && <SourceModal key={`${source.id}-${source.quote || ''}`} api={api} target={source} close={() => setSource(null)} />}
  </div>;
}
