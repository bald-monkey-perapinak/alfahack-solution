import { useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Collapse } from '@alfalab/core-components/collapse';
import { IconButton } from '@alfalab/core-components/icon-button';
import { Link } from '@alfalab/core-components/link';
import { ArrowRightSIcon } from '@alfalab/icons-glyph/ArrowRightSIcon';
import { ArrowRightUpSIcon } from '@alfalab/icons-glyph/ArrowRightUpSIcon';
import { ChevronDownSIcon } from '@alfalab/icons-glyph/ChevronDownSIcon';
import { ShareMIcon } from '@alfalab/icons-glyph/ShareMIcon';
import type { News } from '../../types/news';
import { NewsImage } from './NewsImage';
import { NewsMeta } from './NewsMeta';

export type NewsCardVariant = 'hero' | 'medium' | 'lead' | 'secondary' | 'small';
export interface NewsCardProps {
  news: News;
  variant: NewsCardVariant;
  onFavorite: (id: string) => void;
  onAnalyze: (news: News) => void;
  onShare: (news: News) => void;
}

export function NewsCard({ news, variant, onFavorite, onAnalyze, onShare }: NewsCardProps) {
  const [expanded, setExpanded] = useState(false);
  const compact = variant === 'secondary' || variant === 'small';
  const largeButton = variant === 'hero' || variant === 'medium';
  const hasDetails = Boolean(news.content?.length || news.analystTakeaway);
  const busy = news.analysisStatus === 'processing';
  const titleId = `title-${news.id}`;
  const actionLabel = busy ? 'Готовим анализ' : news.analysisStatus === 'failed' ? 'Повторить анализ'
    : news.analysisStatus === 'not_started' ? 'Анализировать'
    : variant === 'hero' || variant === 'lead' ? 'Открыть анализ' : 'Анализ';

  return (
    <article className={`news-card news-card--${variant}`} aria-labelledby={titleId} id={`news-${news.id}`}>
      {variant === 'small' && <NewsImage image={news.image} />}
      <div className="news-card__main">
        <NewsMeta news={news} onFavorite={onFavorite} />
        <div className="news-card__body">
          <h3 className="news-card__title" id={titleId} title={news.title}>{news.title}</h3>
          {variant !== 'small' && <NewsImage image={news.image} priority={variant === 'hero'} />}
          {(variant === 'medium' || variant === 'lead') && <p className="news-card__summary">{news.summary}</p>}
        </div>
        <div className="news-actions">
          <Button className={`analysis-button${compact ? ' analysis-button--compact' : ''}`}
            size={largeButton ? 40 : 32} view={compact ? 'text' : 'accent'}
            rightAddons={<ArrowRightSIcon aria-hidden="true" />} loading={busy}
            disabled={busy} onClick={() => onAnalyze(news)}>{actionLabel}</Button>
          {variant === 'hero' && hasDetails && (
            <Button view="text" size={40} className="details-button" aria-expanded={expanded}
              aria-controls={`details-${news.id}`} onClick={() => setExpanded(!expanded)}
              rightAddons={<ChevronDownSIcon aria-hidden="true" className={expanded ? 'chevron chevron--expanded' : 'chevron'} />}>
              {expanded ? 'Свернуть' : 'Подробнее'}
            </Button>
          )}
          <Link className="source-link" href={news.source.url} target="_blank" rel="noopener noreferrer"
            rightAddons={<ArrowRightUpSIcon aria-hidden="true" />} title={`Открыть первоисточник: ${news.source.name}`}>
            {compact ? 'Источник' : 'Первоисточник'}
          </Link>
          {(variant === 'hero' || variant === 'medium') && (
            <IconButton className="share-button" size={40} view="transparent" icon={ShareMIcon}
              aria-label={`Поделиться: ${news.title}`} onClick={() => onShare(news)} />
          )}
        </div>
        {variant === 'hero' && hasDetails && (
          <Collapse expanded={expanded} id={`details-${news.id}`} expandedContentClassName="news-details-collapse">
            <div className="news-details-spacing" inert={!expanded}>
              <div className="news-details">
                {news.content?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                {news.analystTakeaway && <aside className="analyst-callout"><strong>Ключевой вывод аналитиков</strong><p>{news.analystTakeaway}</p></aside>}
              </div>
            </div>
          </Collapse>
        )}
      </div>
    </article>
  );
}
