import { lazy, Suspense, useEffect, useState } from 'react';
import { AppHeader } from './components/layout/AppHeader';
import { AppSidebar } from './components/layout/AppSidebar';
import { NewsShowcase } from './pages/NewsShowcase';
import { AnalysisPage } from './pages/AnalysisPage';
import { demoNews } from './mocks/news';
import { getAppRoute, isEntryRoute, routeTitles } from './lib/navigation';
import { clearDemoSession, readDemoSession, startDemoSession } from './lib/auth';
import { PROFILE_STORAGE_KEY } from './lib/profile';
import type { UserProfile } from './types/profile';

const ProfilePage = lazy(() => import('./pages/ProfilePage').then((module) => ({ default: module.ProfilePage })));
const EntryPage = lazy(() => import('./pages/EntryPage').then((module) => ({ default: module.EntryPage })));

/** Hash-маршруты работают и на статическом хостинге без серверных rewrite-правил. */
export function App() {
  const [route, setRoute] = useState(() => getAppRoute(window.location.hash));
  const [hasDemoSession, setHasDemoSession] = useState(readDemoSession);
  // Избранное принадлежит приложению и не сбрасывается при переходе в профиль.
  const [favorites, setFavorites] = useState(() => new Set(demoNews.filter((news) => news.isFavorite).map((news) => news.id)));

  function toggleFavorite(id: string) {
    setFavorites((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function enterDemo({ remember, profile }: { remember: boolean; profile?: UserProfile }) {
    // В хранилище попадают только поля профиля. Пароли сюда не передаются.
    if (profile) window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
    startDemoSession(remember);
    setHasDemoSession(true);
    if (isEntryRoute(route)) {
      window.location.hash = '#/';
      setRoute('feed');
    }
  }

  function signOut() {
    clearDemoSession();
    setHasDemoSession(false);
    setFavorites(new Set(demoNews.filter((news) => news.isFavorite).map((news) => news.id)));
    window.location.hash = '#/login';
    setRoute('login');
  }

  useEffect(() => {
    const syncRoute = () => setRoute(getAppRoute(window.location.hash));
    window.addEventListener('hashchange', syncRoute);
    return () => window.removeEventListener('hashchange', syncRoute);
  }, []);

  useEffect(() => {
    document.title = !hasDemoSession || isEntryRoute(route)
      ? routeTitles[route === 'register' ? 'register' : 'login'] : routeTitles[route];
    if (window.location.hash.startsWith('#/')) window.scrollTo(0, 0);
    // После входа целевая карточка впервые появляется в DOM: восстанавливаем якорь.
    if (hasDemoSession && window.location.hash.startsWith('#news-')) {
      const frame = window.requestAnimationFrame(() => document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: 'start' }));
      return () => window.cancelAnimationFrame(frame);
    }
  }, [route, hasDemoSession]);

  if (!hasDemoSession || isEntryRoute(route)) {
    return (
      <Suspense fallback={<main className="workspace" aria-busy="true">Загрузка входа…</main>}>
        <EntryPage mode={route === 'register' ? 'register' : 'login'} onEnter={enterDemo}
          onModeChange={(mode) => { window.location.hash = mode === 'register' ? '#/register' : '#/login'; }} />
      </Suspense>
    );
  }

  return (
    <>
      <AppHeader profileActive={route === 'profile'} />
      <div className="app-shell">
        <AppSidebar route={route} />
        <div className="app-content">
          {route === 'profile' ? (
            <Suspense fallback={<main className="workspace" aria-busy="true">Загрузка профиля…</main>}><ProfilePage onSignOut={signOut} /></Suspense>
          ) : route === 'analysis' ? <AnalysisPage /> : (
            <NewsShowcase favorites={favorites} onFavorite={toggleFavorite} view={route}
              onViewChange={(view) => { window.location.hash = view === 'favorites' ? '#/favorites' : '#/'; }} />
          )}
        </div>
      </div>
    </>
  );
}
