import { useEffect, useState } from 'react';
import { DocumentLinesMIcon } from '@alfalab/icons-glyph/DocumentLinesMIcon';
import { ArrowRightMIcon } from '@alfalab/icons-glyph/ArrowRightMIcon';
import { Badge, Button, Checkbox, EmptyState, H, LoadingCards, Panel, Text } from '../components/ui';
import { ErrorState } from '../components/ApiFeedback';
import { AnalyticsApi } from '../api/client';
import { dateLabel, publicationLabel, toggleSelection } from '../domain';
import { useResource } from '../hooks/useResource';

export function NewsPage({ api, analyze, source, analysisBusy }: { api: AnalyticsApi; analyze: (ids: number[]) => void; source: (id: number) => void; analysisBusy: boolean }) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const resource = useResource((signal) => api.materials(offset, 6, signal), [api, offset]);
  const page = resource.data;
  useEffect(() => { if (page && offset && !page.items.length && page.total < offset) setOffset(0); }, [page, offset]);
  function changePage(next: number) { setOffset(next); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  return <div className="page-stack news-page">
    <div className="page-heading"><div><H level={1}>Новости и материалы</H><Text>Выберите публикации для персонального анализа</Text></div><Button view="secondary" size={40} onClick={resource.reload} disabled={resource.loading}>Обновить список</Button></div>
    <div className="section-context"><span>Исходные публикации и обзоры банка</span><span>Сначала новые · До 10 в одном задании</span></div>
    {resource.loading ? <LoadingCards /> : resource.error ? <ErrorState error={resource.error} retry={resource.reload} /> : !page?.items.length ? <Panel><EmptyState icon={<DocumentLinesMIcon />} title="Публикаций пока нет" actions={<Button view="secondary" size={40} onClick={resource.reload}>Обновить список</Button>}>Когда появятся материалы, вы сможете выбрать их для анализа.</EmptyState></Panel> : <>
      <div className="news-list">{page.items.map((item) => <Panel key={item.id} className={`news-card ${selected.has(item.id) ? 'news-card--selected' : ''}`}>
        <div className="news-card-heading"><div className="metadata"><span>Публикация: {dateLabel(item.published_at)}</span>{item.material_type === 'bank_analytics' && <Badge>Аналитика Альфа-Банка</Badge>}{item.is_demo && <Badge>Синтетический сценарий</Badge>}</div><Checkbox size={20} checked={selected.has(item.id)} disabled={analysisBusy || selected.size >= 10 && !selected.has(item.id)} aria-label={`Выбрать: ${item.title}`} onChange={() => setSelected((previous) => toggleSelection(previous, item.id))} /></div>
        <H>{item.title}</H>{item.summary && <Text>{item.summary}</Text>}
        <div className="news-card-footer"><Button view="text" size={32} onClick={() => source(item.id)} className="source-link">Посмотреть первоисточник ↗</Button><Button view="secondary" size={40} disabled={analysisBusy} onClick={() => analyze([item.id])}>Анализировать</Button></div>
      </Panel>)}</div>
      <div className="pagination"><span className="caption">{offset + 1}–{offset + page.items.length} из {page.total} публикаций</span><div className="actions"><Button view="secondary" size={32} disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - 6))}>Назад</Button><span className="caption">{Math.floor(offset / 6) + 1} / {Math.max(1, Math.ceil(page.total / 6))}</span><Button view="secondary" size={32} disabled={offset + page.limit >= page.total} onClick={() => changePage(offset + 6)}>Далее</Button></div></div>
    </>}
    {selected.size > 0 && <div className="selection-bar" role="region" aria-label="Выбранные публикации"><div><strong aria-live="polite">Выбрано: {selected.size} {publicationLabel(selected.size)}</strong><span className="caption">{selected.size === 10 ? 'Достигнут максимум — 10 публикаций' : 'Не более 10 публикаций за один запуск'}</span></div><div className="actions"><Button view="text" size={40} onClick={() => setSelected(new Set())}>Снять выделение</Button><Button view="accent" size={40} className="accent-button" disabled={analysisBusy} rightAddons={<ArrowRightMIcon />} onClick={() => analyze([...selected])}>Проанализировать ({selected.size})</Button></div></div>}
  </div>;
}
