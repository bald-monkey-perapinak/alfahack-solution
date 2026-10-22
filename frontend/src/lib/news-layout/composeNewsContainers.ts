import { createNewsGroup, type News, type NewsGroup } from '../../types/news.ts';

export interface NewsLayoutPolicy {
  /** Доля Hero, рассчитываемая отдельно для срочной и несрочной частей. */
  heroRatio: number;
  maxHeroCount: number;
  highlightThreshold: number;
  /** Лимит highlights для несрочных. На срочную часть не влияет. */
  maxHighlights: number;
  heroThreshold: number;
  /** Обычный Hero должен быть важнее медианы как минимум на это значение. */
  heroMedianMargin: number;
  mediumThreshold: number;
  duoMaxGap: number;
  trioMinGap: number;
}

export const DEFAULT_NEWS_LAYOUT_POLICY: Readonly<NewsLayoutPolicy> = Object.freeze({
  heroRatio: 0.2,
  maxHeroCount: 3,
  highlightThreshold: 95,
  maxHighlights: 3,
  heroThreshold: 80,
  heroMedianMargin: 10,
  mediumThreshold: 50,
  duoMaxGap: 10,
  trioMinGap: 10,
});

export interface ComposeNewsOptions {
  groupId?: string;
  groupTitle?: string;
  policy?: Partial<NewsLayoutPolicy>;
}

export type ContainerReason =
  | 'highlight'
  | 'important'
  | 'balanced-pair'
  | 'dominant-lead'
  | 'compact'
  | 'remainder'
  | 'single-item';

/** Совместим с существующим NewsContainer через его prop group. */
export type ComposedNewsContainer = NewsGroup & {
  /** Исходная группа: расстановка не смешивает контейнеры разных групп. */
  sourceGroupId: string;
  placement: 'urgent' | 'highlights' | 'group';
  reason: ContainerReason;
};

export interface NewsImportanceStats {
  count: number;
  mean: number | null;
  median: number | null;
  /** Категории не пересекаются. high не включает exceptional. */
  exceptional: number;
  high: number;
  medium: number;
  low: number;
}

function resolvePolicy(overrides: Partial<NewsLayoutPolicy> = {}): NewsLayoutPolicy {
  const policy = { ...DEFAULT_NEWS_LAYOUT_POLICY, ...overrides };
  for (const [key, value] of Object.entries(policy)) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new TypeError(`Настройка ${key} должна быть конечным числом`);
    }
  }
  if (policy.heroRatio < 0 || policy.heroRatio > 1) {
    throw new RangeError('heroRatio должен быть от 0 до 1');
  }
  for (const key of ['maxHeroCount', 'maxHighlights'] as const) {
    if (!Number.isInteger(policy[key]) || policy[key] < 0) {
      throw new RangeError(`${key} должен быть неотрицательным целым числом`);
    }
  }
  for (const key of ['highlightThreshold', 'heroThreshold', 'heroMedianMargin', 'mediumThreshold', 'duoMaxGap', 'trioMinGap'] as const) {
    if (policy[key] < 0 || policy[key] > 100) {
      throw new RangeError(`${key} должен быть от 0 до 100`);
    }
  }
  if (policy.mediumThreshold > policy.heroThreshold || policy.heroThreshold > policy.highlightThreshold) {
    throw new RangeError('Пороги должны соблюдать mediumThreshold <= heroThreshold <= highlightThreshold');
  }
  return policy;
}

/** Не меняет входной массив и объекты. При равенстве оценок: дата, затем id. */
function sortAndValidate(news: readonly News[]): News[] {
  const ids = new Set<string>();
  return news.map((item) => {
    if (typeof item.id !== 'string' || !item.id.trim()) {
      throw new TypeError('Новость должна иметь непустой строковый id');
    }
    if (ids.has(item.id)) throw new Error(`Повторяющийся id новости: ${item.id}`);
    ids.add(item.id);
    if (typeof item.importance !== 'number' || !Number.isFinite(item.importance)
      || item.importance < 0 || item.importance > 100) {
      throw new RangeError(`Важность новости ${item.id} должна быть от 0 до 100`);
    }
    const timestamp = Date.parse(item.publishedAt);
    if (!Number.isFinite(timestamp)) throw new TypeError(`Некорректная дата новости ${item.id}`);
    return { item, timestamp };
  }).sort((a, b) => b.item.importance - a.item.importance
    || b.timestamp - a.timestamp
    || (a.item.id < b.item.id ? -1 : a.item.id > b.item.id ? 1 : 0))
    .map(({ item }) => item);
}

function calculateStats(sorted: readonly News[], policy: NewsLayoutPolicy): NewsImportanceStats {
  const count = sorted.length;
  const middle = Math.floor(count / 2);
  const stats: NewsImportanceStats = {
    count,
    mean: count ? sorted.reduce((sum, item) => sum + item.importance, 0) / count : null,
    median: count ? count % 2 ? sorted[middle].importance
      : (sorted[middle - 1].importance + sorted[middle].importance) / 2 : null,
    exceptional: 0, high: 0, medium: 0, low: 0,
  };
  for (const item of sorted) {
    if (item.importance >= policy.highlightThreshold) stats.exceptional++;
    else if (item.importance >= policy.heroThreshold) stats.high++;
    else if (item.importance >= policy.mediumThreshold) stats.medium++;
    else stats.low++;
  }
  return stats;
}

/** Статистика для настройки правил. Среднее не определяет формат карточки. */
export function getNewsImportanceStats(
  news: readonly News[],
  overrides?: Partial<NewsLayoutPolicy>,
): NewsImportanceStats {
  const policy = resolvePolicy(overrides);
  return calculateStats(sortAndValidate(news), policy);
}

function isBalancedPair(items: readonly News[], offset: number, policy: NewsLayoutPolicy): boolean {
  const first = items[offset];
  const second = items[offset + 1];
  return Boolean(first && second && second.importance >= policy.mediumThreshold
    && first.importance - second.importance <= policy.duoMaxGap);
}

/** Любое число >= 6, а также 0, 3, 4 представимо суммой троек и четвёрок. */
function canPackCompact(count: number): boolean {
  return count === 0 || count === 3 || count === 4 || count >= 6;
}

function pickSize(items: readonly News[], offset: number, policy: NewsLayoutPolicy): 2 | 3 | 4 {
  const remaining = items.length - offset;
  if (remaining === 2) return 2;
  if (remaining === 3) return 3;
  if (isBalancedPair(items, offset, policy)
    && (remaining !== 4 || isBalancedPair(items, offset + 2, policy))) return 2;
  if (remaining === 4) return 4;
  // Пять невозможно разложить только на 3/4: ставим Duo, затем Trio.
  if (remaining === 5) return 2;

  const dominant = items[offset].importance - items[offset + 1].importance >= policy.trioMinGap;
  const candidates: readonly (3 | 4)[] = dominant ? [3, 4] : [4, 3];
  for (const size of candidates) {
    const tailCount = remaining - size;
    if (tailCount === 1) continue;
    const lowTail = items[offset + size]?.importance < policy.mediumThreshold;
    // Не оставляем 2 или 5 низкоприоритетных новостей, если возможно обойтись Trio/Quartet.
    if (lowTail && !canPackCompact(tailCount)) continue;
    return size;
  }
  // При remaining >= 6 один из вариантов 3/4 всегда подходит.
  throw new Error('Не удалось скомпоновать остаток новостей');
}

/** Один механизм упаковки для обеих частей; срочные Hero остаются внутри urgent. */
function composeSection(
  sorted: readonly News[],
  placement: 'urgent' | 'group',
  policy: NewsLayoutPolicy,
  groupId: string,
  groupTitle: string,
): ComposedNewsContainer[] {
  const containers: ComposedNewsContainer[] = [];
  if (!sorted.length) return containers;

  function add(items: News[], target: ComposedNewsContainer['placement'], reason: ContainerReason) {
    const id = [groupId, target, ...items.map((item) => item.id)].map(encodeURIComponent).join(':');
    const title = target === 'urgent' ? 'Срочные новости'
      : target === 'highlights' ? 'Самое главное' : groupTitle;
    const group = createNewsGroup(id, title, items);
    if (group) containers.push({ ...group, sourceGroupId: groupId, placement: target, reason });
  }

  const stats = calculateStats(sorted, policy);
  const heroLimit = Math.min(policy.maxHeroCount, Math.floor(sorted.length * policy.heroRatio));
  const allowSmallExceptional = sorted.length < 5 && policy.heroRatio > 0 && policy.maxHeroCount > 0;
  const exceptionalBudget = allowSmallExceptional ? Math.max(1, heroLimit) : heroLimit;
  const exceptionalLimit = placement === 'group'
    ? Math.min(policy.maxHighlights, exceptionalBudget) : exceptionalBudget;
  let exceptionalHeroCount = Math.min(stats.exceptional, exceptionalLimit);
  const heroCutoff = Math.max(policy.heroThreshold, stats.median! + policy.heroMedianMargin);
  let ordinaryHeroCount = 0;
  while (exceptionalHeroCount + ordinaryHeroCount < heroLimit
    && sorted[exceptionalHeroCount + ordinaryHeroCount]?.importance >= heroCutoff) {
    ordinaryHeroCount++;
  }

  // Не делаем случайный дополнительный Hero из последней новости.
  if (sorted.length > 1 && sorted.length - exceptionalHeroCount - ordinaryHeroCount === 1) {
    if (ordinaryHeroCount) ordinaryHeroCount--;
    else if (exceptionalHeroCount) exceptionalHeroCount--;
  }

  for (let i = 0; i < exceptionalHeroCount; i++) {
    add([sorted[i]], placement === 'group' ? 'highlights' : 'urgent', placement === 'group' ? 'highlight' : 'important');
  }
  for (let i = exceptionalHeroCount; i < exceptionalHeroCount + ordinaryHeroCount; i++) {
    add([sorted[i]], placement, 'important');
  }
  let offset = exceptionalHeroCount + ordinaryHeroCount;
  if (sorted.length - offset === 1) {
    add([sorted[offset]], placement, 'single-item');
    return containers;
  }
  while (offset < sorted.length) {
    const size = pickSize(sorted, offset, policy);
    const reason: ContainerReason = size === 2
      ? isBalancedPair(sorted, offset, policy) ? 'balanced-pair' : 'remainder'
      : size === 3 && sorted[offset].importance - sorted[offset + 1].importance >= policy.trioMinGap
        ? 'dominant-lead' : 'compact';
    add(sorted.slice(offset, offset + size), placement, reason);
    offset += size;
  }
  return containers;
}

/**
 * Компоновка ОДНОЙ полной группы, без выбора тем и без React.
 * Каждый материал встречается ровно один раз. Порядок разделов: urgent, highlights, group;
 * внутри разделов — по важности, дате и id. Обе части используют общие правила упаковки,
 * но независимо считают медиану и бюджет Hero. Срочные никогда не переходят в highlights.
 * Исключения для каждой части: единственная новость отображается Hero; в группе 2–4
 * допускается один exceptional Hero, если после него остаётся минимум две новости.
 */
export function composeNewsContainers(
  news: readonly News[],
  options: ComposeNewsOptions = {},
): ComposedNewsContainer[] {
  const policy = resolvePolicy(options.policy);
  const groupId = options.groupId ?? 'news-group';
  const groupTitle = options.groupTitle ?? 'Новости';
  if (!groupId.trim()) throw new TypeError('groupId не должен быть пустым');
  const allSorted = sortAndValidate(news);
  const urgent = allSorted.filter((item) => item.urgency === 'urgent');
  const regular = allSorted.filter((item) => item.urgency !== 'urgent');
  return [
    ...composeSection(urgent, 'urgent', policy, groupId, groupTitle),
    ...composeSection(regular, 'group', policy, groupId, groupTitle),
  ];
}
