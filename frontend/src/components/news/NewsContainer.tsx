import type { NewsGroup } from '../../types/news';
import { NewsCard, type NewsCardProps } from './NewsCard';
import './news.css';

type Props = Pick<NewsCardProps, 'onFavorite' | 'onAnalyze' | 'onShare'> & { group: NewsGroup };

/** CSS отвечает за сетку, карточки — только за собственный формат. */
export function NewsContainer({ group, ...actions }: Props) {
  return (
    <div className={`news-container news-container--${group.variant}`} data-layout={group.variant} data-container-id={group.id}>
      {group.variant === 'hero' && <NewsCard news={group.items[0]} variant="hero" {...actions} />}
      {group.variant === 'duo' && group.items.map((news) => <NewsCard key={news.id} news={news} variant="medium" {...actions} />)}
      {group.variant === 'trio' && <>
        <NewsCard news={group.items[0]} variant="lead" {...actions} />
        <div className="news-container__stack">
          {group.items.slice(1).map((news) => <NewsCard key={news.id} news={news} variant="secondary" {...actions} />)}
        </div>
      </>}
      {group.variant === 'quartet' && group.items.map((news) => <NewsCard key={news.id} news={news} variant="small" {...actions} />)}
    </div>
  );
}
