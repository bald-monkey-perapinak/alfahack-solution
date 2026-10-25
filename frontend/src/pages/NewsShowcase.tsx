import { useEffect, useMemo, useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Input } from '@alfalab/core-components/input';
import { Modal } from '@alfalab/core-components/modal';
import { Tag } from '@alfalab/core-components/tag';
import { Tabs, Tab } from '@alfalab/core-components/tabs';
import { MagnifierMIcon } from '@alfalab/icons-glyph/MagnifierMIcon';
import { FlameSIcon } from '@alfalab/icons-glyph/FlameSIcon';
import { NewsFeedSection } from '../components/news/NewsFeedSection';
import { buildNewsFeed } from '../lib/news-layout';
import { demoNews as allNews } from '../mocks/news';
import { topics, type News, type Topic } from '../types/news';

export function NewsShowcase({ favorites, onFavorite: toggleFavorite, view, onViewChange }: {
  favorites: ReadonlySet<string>;
  onFavorite: (id: string) => void;
  view: 'feed' | 'favorites';
  onViewChange: (view: 'feed' | 'favorites') => void;
}) {
  const [topic, setTopic] = useState<Topic | 'all'>('all');
  const [urgentOnly, setUrgentOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedNews, setSelectedNews] = useState<News | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const filteredNews = useMemo(() => allNews
    .map((news) => ({ ...news, isFavorite: favorites.has(news.id) })).filter((news) => {
      const matchesText = `${news.title} ${news.summary} ${news.source.name} ${news.topic}`.toLocaleLowerCase('ru').includes(search.trim().toLocaleLowerCase('ru'));
      return matchesText && (view !== 'favorites' || news.isFavorite) && (topic === 'all' || news.topic === topic) && (!urgentOnly || news.urgency === 'urgent');
    }), [favorites, view, topic, urgentOnly, search]);
  const sections = useMemo(() => buildNewsFeed(filteredNews), [filteredNews]);
  const visibleCount = filteredNews.length;

  async function shareNews(news: News) {
    const url = new URL(window.location.href);
    url.hash = `news-${news.id}`;
    try {
      await navigator.clipboard.writeText(url.toString());
      setNotice('Ссылка на новость скопирована');
    } catch {
      setNotice('Не удалось скопировать ссылку. Разрешите доступ к буферу обмена.');
    }
  }

  function resetFilters() {
    setSearch(''); setTopic('all'); setUrgentOnly(false);
  }

  return (
    <>
      <main className="workspace">
        <div className="page-heading">
          <div><p className="eyebrow">ИНФОРМАЦИЯ ДЛЯ ВАШЕГО БИЗНЕСА</p><h1>{view === 'favorites' ? 'Избранное' : 'Новости и аналитика'}</h1><p className="page-description">{view === 'favorites' ? 'Сохранённые новости — всё важное под рукой.' : 'События, которые влияют на ваш бизнес. Главное — с AI-анализом.'}</p></div>
          <div className="search-field"><Input size={40} block value={search} onChange={(event) => setSearch(event.target.value)}
            leftAddons={<MagnifierMIcon aria-hidden="true" />} placeholder="Поиск по новостям и темам" aria-label="Поиск по новостям и темам" clear /></div>
        </div>
        <div className="feed-controls">
          <Tabs selectedId={view === 'favorites' ? 'favorites' : 'all'} onChange={(_, { selectedId }) => onViewChange(selectedId === 'favorites' ? 'favorites' : 'feed')}
            view="secondary" tagShape="rounded" tagView="filled" size="s" className="feed-tabs">
            <Tab id="all" title={<>Все новости <span className="tab-count">{allNews.length}</span></>} />
            <Tab id="favorites" title={<>Избранное <span className="tab-count">{favorites.size}</span></>} />
          </Tabs>
          <div className="topic-row" role="group" aria-label="Фильтры новостей">
            <div className="topic-list">
              {(['all', ...topics] as const).map((value) => <Tag key={value} size={32} shape="rounded" view="filled"
                checked={topic === value} aria-pressed={topic === value} className={`topic-tag${topic === value ? ' topic-tag--active' : ''}`}
                onClick={() => setTopic(value)}>{value === 'all' ? 'Все темы' : value}</Tag>)}
            </div>
            <Tag size={32} shape="rounded" view="filled" checked={urgentOnly} aria-pressed={urgentOnly}
              leftAddons={<FlameSIcon aria-hidden="true" />} className={`urgent-tag${urgentOnly ? ' urgent-tag--active' : ''}`}
              onClick={() => setUrgentOnly(!urgentOnly)}>Только срочные</Tag>
          </div>
        </div>
        <div className="feed-caption"><span>Демонстрационная лента <span aria-hidden="true">·</span> {visibleCount} из {allNews.length} материалов</span><span>Главное и подборки по темам</span></div>
        <div className="news-feed">
          {sections.map((section) => <NewsFeedSection key={section.id} section={section} onFavorite={toggleFavorite}
            onAnalyze={(news) => { setSelectedNews(news); setAnalysisOpen(true); }} onShare={shareNews} />)}
          {sections.length === 0 && <div className="empty-state"><MagnifierMIcon aria-hidden="true" /><h2>{view === 'favorites' && favorites.size === 0 ? 'В избранном пока нет новостей' : 'Новостей пока нет'}</h2><p>{view === 'favorites' && favorites.size === 0 ? 'Сохраняйте новости с помощью закладки в карточке.' : 'Попробуйте другую тему или измените условия поиска.'}</p>{view === 'favorites' && favorites.size === 0 ? <Button href="#/" size={40} view="secondary">Перейти к новостям</Button> : <Button size={40} view="secondary" onClick={resetFilters}>Сбросить фильтры</Button>}</div>}
        </div>
        <footer className="demo-footer">Пример интерфейса по дизайн-системе. Новости, время и оценки ИИ — демонстрационные данные.</footer>
      </main>
      <Modal open={analysisOpen} onClose={() => setAnalysisOpen(false)} hasCloser size={600}>
        <Modal.Header title="Предпросмотр анализа" />
        <Modal.Content><div className="analysis-preview"><span className="preview-label">Демонстрационный материал</span><h2>{selectedNews?.title}</h2>
          <p>{selectedNews?.summary || 'Краткая выжимка для этого материала ещё не подготовлена.'}</p>
          <div className="analyst-callout"><strong>Полный анализ появится позже</strong><p>Здесь будет отдельная страница с влиянием на бизнес, рекомендациями и данными компании.</p></div></div></Modal.Content>
        <Modal.Footer><Button size={40} view="secondary" onClick={() => setAnalysisOpen(false)}>Вернуться к новостям</Button></Modal.Footer>
      </Modal>
      <div className={`toast${notice ? ' toast--visible' : ''}`} role="status" aria-live="polite">{notice}</div>
    </>
  );
}
