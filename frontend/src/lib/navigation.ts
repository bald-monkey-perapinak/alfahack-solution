export type AppRoute = 'feed' | 'favorites' | 'analysis' | 'profile' | 'login' | 'register';

export function isEntryRoute(route: AppRoute): route is 'login' | 'register' {
  return route === 'login' || route === 'register';
}

export function getAppRoute(hash: string): AppRoute {
  if (hash === '#/favorites') return 'favorites';
  if (hash === '#/analysis') return 'analysis';
  if (hash === '#/profile') return 'profile';
  if (hash === '#/login') return 'login';
  if (hash === '#/register') return 'register';
  // Старые ссылки #news-id по-прежнему открывают ленту.
  return 'feed';
}

export const routeTitles: Record<AppRoute, string> = {
  feed: 'Новости и аналитика — Альфа-Бизнес',
  favorites: 'Избранное — Альфа-Бизнес',
  analysis: 'Анализ — Альфа-Бизнес',
  profile: 'Профиль — Альфа-Бизнес',
  login: 'Вход в кабинет — Альфа-Бизнес',
  register: 'Регистрация — Альфа-Бизнес',
};
