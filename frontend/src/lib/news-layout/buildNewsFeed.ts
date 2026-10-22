import { topics, type News, type Topic } from '../../types/news.ts';
import { arrangeNewsContainers, type ContainerArrangementPolicy } from './arrangeNewsContainers.ts';
import {
  composeNewsContainers,
  getNewsImportanceStats,
  DEFAULT_NEWS_LAYOUT_POLICY,
  type ComposedNewsContainer,
  type NewsLayoutPolicy,
} from './composeNewsContainers.ts';

export interface NewsFeedSection {
  id: string;
  title: string;
  placement: ComposedNewsContainer['placement'];
  topic?: Topic;
  count: number;
  containers: ComposedNewsContainer[];
}

export interface BuildNewsFeedOptions {
  policy?: Partial<NewsLayoutPolicy>;
  arrangement?: Partial<ContainerArrangementPolicy>;
}

function compareHighlights(a: ComposedNewsContainer, b: ComposedNewsContainer): number {
  const first = a.items[0];
  const second = b.items[0];
  return second.importance - first.importance
    || Date.parse(second.publishedAt) - Date.parse(first.publishedAt)
    || (first.id < second.id ? -1 : first.id > second.id ? 1 : 0);
}

/** Кандидат, не прошедший общий лимит highlights, остаётся Hero своей темы. */
function returnToTopic(container: ComposedNewsContainer, title: Topic): ComposedNewsContainer {
  return {
    ...container,
    id: [container.sourceGroupId, 'group', ...container.items.map((item) => item.id)].map(encodeURIComponent).join(':'),
    title,
    placement: 'group',
    reason: 'important',
  };
}

/**
 * Полный экран: плоские новости с вручную заданным topic → разделы с готовой расстановкой.
 * Срочные компонуются вместе, независимо от тем. Несрочные — отдельно по каждой теме.
 * Общий лимит highlights применяется после отбора кандидатов из тем; потерь и дублей нет.
 */
export function buildNewsFeed(
  news: readonly News[],
  options: BuildNewsFeedOptions = {},
): NewsFeedSection[] {
  // Проверяем весь вход, в том числе повторные id между разными темами.
  getNewsImportanceStats(news, options.policy);
  const byTopic = new Map<Topic, News[]>();
  const urgent: News[] = [];
  for (const item of news) {
    if (!topics.includes(item.topic)) throw new Error(`Неизвестная тема новости ${item.id}: ${item.topic}`);
    if (item.urgency === 'urgent') urgent.push(item);
    else {
      const items = byTopic.get(item.topic) ?? [];
      items.push(item);
      byTopic.set(item.topic, items);
    }
  }

  const urgentContainers = composeNewsContainers(urgent, { groupId: 'feed-urgent', policy: options.policy });
  const composedTopics = topics.map((topic) => ({
    topic,
    containers: composeNewsContainers(byTopic.get(topic) ?? [], {
      groupId: `topic:${topic}`, groupTitle: topic, policy: options.policy,
    }),
  }));
  const maxHighlights = options.policy?.maxHighlights ?? DEFAULT_NEWS_LAYOUT_POLICY.maxHighlights;
  const highlights = composedTopics.flatMap(({ containers }) => containers)
    .filter(({ placement }) => placement === 'highlights').sort(compareHighlights).slice(0, maxHighlights);
  const highlightedIds = new Set(highlights.map(({ id }) => id));
  const sections: NewsFeedSection[] = [];

  function addSection(id: string, title: string, placement: NewsFeedSection['placement'],
    containers: ComposedNewsContainer[], topic?: Topic) {
    const arranged = arrangeNewsContainers(containers, options.arrangement);
    if (!arranged.length) return;
    sections.push({ id, title, placement, topic, containers: arranged,
      count: arranged.reduce((count, container) => count + container.items.length, 0) });
  }

  addSection('urgent', 'Срочные новости', 'urgent', urgentContainers);
  addSection('highlights', 'Самое главное', 'highlights', highlights);
  for (const { topic, containers } of composedTopics) {
    const regular = containers.filter(({ id }) => !highlightedIds.has(id))
      .map((container) => container.placement === 'highlights' ? returnToTopic(container, topic) : container);
    addSection(`topic:${topic}`, topic, 'group', regular, topic);
  }
  return sections;
}
