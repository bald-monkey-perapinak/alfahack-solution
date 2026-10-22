import { IconButton } from '@alfalab/core-components/icon-button';
import { BookmarkLineMIcon } from '@alfalab/icons-glyph/BookmarkLineMIcon';
import { BookmarkMIcon } from '@alfalab/icons-glyph/BookmarkMIcon';
import { FlameSIcon } from '@alfalab/icons-glyph/FlameSIcon';
import { PencilSIcon } from '@alfalab/icons-glyph/PencilSIcon';
import type { News } from '../../types/news';

const timeFormatter = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' });

export function NewsMeta({ news, onFavorite }: { news: News; onFavorite: (id: string) => void }) {
  return (
    <div className="news-meta">
      <div className="news-meta__info">
        <span className="news-meta__source">{news.source.name}</span>
        <span aria-hidden="true" className="news-meta__dot">·</span>
        <time dateTime={news.publishedAt}>{timeFormatter.format(new Date(news.publishedAt))}</time>
        {news.urgency !== 'normal' && (
          <span className={`news-label news-label--${news.urgency}`}>
            {news.urgency === 'urgent' ? <FlameSIcon aria-hidden="true" /> : <PencilSIcon aria-hidden="true" />}
            {news.urgency === 'urgent' ? 'Срочно' : 'Планируется'}
          </span>
        )}
      </div>
      <div className="news-meta__aside">
        {news.confidence && (
          <span className="confidence" title={`Пример оценки ИИ: ${news.confidence.value} из 5. Методика пока не определена.`}>
            <span className="confidence__stars" aria-hidden="true">{'★'.repeat(Math.round(news.confidence.value))}{'☆'.repeat(5 - Math.round(news.confidence.value))}</span>
            <span aria-label={`Демонстрационная оценка ИИ: ${news.confidence.value} из 5`}>{news.confidence.value}/5</span>
          </span>
        )}
        <IconButton className={`favorite-button${news.isFavorite ? ' favorite-button--active' : ''}`}
          size={40} view="transparent" icon={news.isFavorite ? BookmarkMIcon : BookmarkLineMIcon}
          aria-label={`${news.isFavorite ? 'Убрать из избранного' : 'В избранное'}: ${news.title}`}
          aria-pressed={news.isFavorite} onClick={() => onFavorite(news.id)} />
      </div>
    </div>
  );
}
