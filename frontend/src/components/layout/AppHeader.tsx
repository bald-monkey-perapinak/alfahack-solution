import { Button } from '@alfalab/core-components/button';
import { UserMIcon } from '@alfalab/icons-glyph/UserMIcon';

export function AppHeader({ profileActive }: { profileActive: boolean }) {
  return (
    <header className="app-header">
      <a href="#/" className="brand" aria-label="Альфа-Бизнес — главная">
        <span className="brand__mark" aria-hidden="true">А</span>
        <span>Альфа-Бизнес<span className="brand__divider" /> <span className="brand__service">Новости и аналитика</span></span>
      </a>
      <Button href="#/profile" view="text" size={40} aria-label="Профиль"
        className={`app-profile-link${profileActive ? ' app-profile-link--active' : ''}`} aria-current={profileActive ? 'page' : undefined}>
        <span className="app-profile-link-content"><UserMIcon aria-hidden="true" /><span>Профиль</span></span>
      </Button>
    </header>
  );
}
