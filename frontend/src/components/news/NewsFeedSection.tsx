import type { NewsFeedSection as FeedSection } from '../../lib/news-layout';
import type { NewsCardProps } from './NewsCard';
import { NewsContainer } from './NewsContainer';

type Props = Pick<NewsCardProps, 'onFavorite' | 'onAnalyze' | 'onShare'> & { section: FeedSection };
const pluralRules = new Intl.PluralRules('ru');

export function NewsFeedSection({ section, ...actions }: Props) {
  const plural = pluralRules.select(section.count);
  const word = plural === 'one' ? 'материал' : plural === 'few' ? 'материала' : 'материалов';
  return (
    <section className="news-section" aria-labelledby={`section-${section.id}`}
      data-feed-section={section.id} data-placement={section.placement}>
      <div className="news-section__heading">
        <h2 id={`section-${section.id}`}>{section.title}</h2>
        <span>{section.count} {word}</span>
      </div>
      <div className="news-section__containers">
        {section.containers.map((group) => <NewsContainer key={group.id} group={group} {...actions} />)}
      </div>
    </section>
  );
}
