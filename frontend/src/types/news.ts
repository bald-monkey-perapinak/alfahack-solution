export const topics = [
  'Макроэкономика',
  'Регуляторы и ЦБ',
  'Финансы и Банки',
  'Налоги и Право',
  'Логистика и ВЭД',
] as const;

export type Topic = (typeof topics)[number];
export type NewsUrgency = 'normal' | 'urgent' | 'planned';
export type AnalysisStatus = 'not_started' | 'processing' | 'ready' | 'failed';

export interface NewsSource {
  name: string;
  url: string;
}

export interface NewsImage {
  url: string;
  alt: string;
  position?: string;
}

export interface Confidence {
  value: number;
  scale: 5;
  isDemo: boolean;
}

export interface News {
  id: string;
  title: string;
  /** Важность для бизнеса от 0 до 100. Не связана с достоверностью анализа. */
  importance: number;
  /** Краткая аналитическая выжимка для Duo и главной карточки Trio. */
  summary: string;
  content?: string[];
  analystTakeaway?: string;
  source: NewsSource;
  publishedAt: string;
  topic: Topic;
  image?: NewsImage;
  urgency: NewsUrgency;
  confidence?: Confidence;
  isFavorite: boolean;
  analysisStatus: AnalysisStatus;
}

interface GroupBase {
  id: string;
  title: string;
}

/** Порядок важен: первый элемент Trio — главная новость. */
export type NewsGroup = GroupBase & (
  | { variant: 'hero'; items: readonly [News] }
  | { variant: 'duo'; items: readonly [News, News] }
  | { variant: 'trio'; items: readonly [News, News, News] }
  | { variant: 'quartet'; items: readonly [News, News, News, News] }
);

/** Перестраивает контейнер после фильтрации, не оставляя пустых ячеек. */
export function createNewsGroup(id: string, title: string, items: News[]): NewsGroup | null {
  const [a, b, c, d] = items;
  if (!a) return null;
  if (items.length > 4) throw new Error('NewsGroup поддерживает от 1 до 4 новостей');
  if (d && c && b) return { id, title, variant: 'quartet', items: [a, b, c, d] };
  if (c && b) return { id, title, variant: 'trio', items: [a, b, c] };
  if (b) return { id, title, variant: 'duo', items: [a, b] };
  return { id, title, variant: 'hero', items: [a] };
}
