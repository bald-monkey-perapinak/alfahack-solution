import { Button } from '@alfalab/core-components/button';
import { DocumentLinesMIcon } from '@alfalab/icons-glyph/DocumentLinesMIcon';
import { BookmarkLineMIcon } from '@alfalab/icons-glyph/BookmarkLineMIcon';
import { BarChartMIcon } from '@alfalab/icons-glyph/BarChartMIcon';
import type { AppRoute } from '../../lib/navigation';
import './layout.css';

const items = [
  { route: 'feed', href: '#/', label: 'Лента новостей', icon: DocumentLinesMIcon },
  { route: 'favorites', href: '#/favorites', label: 'Избранное', icon: BookmarkLineMIcon },
  { route: 'analysis', href: '#/analysis', label: 'Анализ', icon: BarChartMIcon },
] as const;

export function AppSidebar({ route }: { route: AppRoute }) {
  return (
    <aside className="app-sidebar">
      <nav className="sidebar-navigation" aria-label="Основная навигация">
        {items.map(({ route: itemRoute, href, label, icon: Icon }) => (
          <Button key={itemRoute} href={href} view="text" size={48}
            className={`sidebar-link${route === itemRoute ? ' sidebar-link--active' : ''}`}
            aria-current={route === itemRoute ? 'page' : undefined} aria-label={label} title={label}>
            <span className="sidebar-link-content"><Icon aria-hidden="true" /><span className="sidebar-link-label">{label}</span></span>
          </Button>
        ))}
      </nav>
    </aside>
  );
}
