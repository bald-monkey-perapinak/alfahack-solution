import { useEffect, useState } from 'react';
import { BarChartMIcon } from '@alfalab/icons-glyph/BarChartMIcon';
import { PlusMIcon } from '@alfalab/icons-glyph/PlusMIcon';
import { ArrowRightMIcon } from '@alfalab/icons-glyph/ArrowRightMIcon';
import { ClockMIcon } from '@alfalab/icons-glyph/ClockMIcon';
import { MagnifierMIcon } from '@alfalab/icons-glyph/MagnifierMIcon';
import { Badge, Button, Callout, Disclosure, EmptyState, H, LoadingCards, Panel, ProgressBar, Spinner, Text } from '../components/ui';
import { ErrorState, InlineError } from '../components/ApiFeedback';
import { AnalyticsApi, ApiError } from '../api/client';
import type { GenerationMode, Job } from '../api/types';
import { dateLabel, percent } from '../domain';
import { useResource } from '../hooks/useResource';

export function ModeBadge({ mode }: { mode?: GenerationMode }) {
  return <Badge tone={mode === 'live' ? 'blue' : 'neutral'}>{mode === 'live' ? 'С использованием LLM' : mode === 'offline' ? 'Анализ по правилам · Без LLM' : 'Режим не указан'}</Badge>;
}
function JobTotals({ job }: { job: Job }) {
  return <div className="result-totals"><span>Обработано: {job.summary.processed ?? '—'}</span><span>Создано: {job.summary.created ?? '—'}</span><span>Пропущено: {job.summary.skipped ?? '—'}</span></div>;
}
export function AnalyticsPage({ api, revision, job, jobError, restoring, retryJob, clearJob, context, prepare, onSourceChoice }: {
  api: AnalyticsApi; revision: number; job: Job | null; jobError: unknown; restoring: boolean; retryJob: () => void; clearJob: () => void;
  context: string; prepare: () => void; onSourceChoice: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const feed = useResource(async (signal) => {
    const page = await api.feed(offset, 6, signal);
    const details = await Promise.allSettled(page.items.map((item) => api.insight(item.id, signal)));
    const previews = Object.fromEntries(details.flatMap((result) => result.status === 'fulfilled' ? [[result.value.id, result.value]] : []));
    return { ...page, previews };
  }, [api, offset, revision]);
  const page = feed.data;
  useEffect(() => { if (page && offset && page.total <= offset) setOffset(0); }, [page, offset]);
  const processing = restoring || job?.status === 'pending' || job?.status === 'running';
  const noResults = job?.status === 'completed' && job.summary.created === 0;
  return <div className="page-stack">
    <div className="page-heading"><div><H level={1}>Моя аналитика</H><Text className="context-line">{context}</Text></div><div className="heading-action"><Button view="accent" size={40} className="accent-button" leftAddons={<PlusMIcon />} onClick={prepare} disabled={processing}>{page?.total ? 'Подготовить новую подборку' : 'Подготовить аналитику'}</Button>{Boolean(page?.total) && <span className="caption">Новый анализ последних публикаций</span>}</div></div>
    {Boolean(jobError) && <InlineError error={jobError} retry={retryJob} />}
    {jobError instanceof ApiError && jobError.status === 404 && <Button view="text" size={32} onClick={clearJob}>Убрать недоступное задание</Button>}
    {processing && <Panel className="job-panel"><div className="job-top"><div className="job-icon"><Spinner visible preset={24} /></div><Badge tone={job?.status === 'running' ? 'blue' : 'neutral'}>{restoring ? 'Проверка статуса' : job?.status === 'pending' ? 'В очереди' : 'В работе'}</Badge></div><H>{restoring ? 'Восстанавливаем статус задания' : job?.status === 'pending' ? 'Задание ожидает обработки' : 'Аналитика готовится'}</H><Text>{job?.status === 'pending' ? 'Публикации приняты сервером. Задание ожидает своей очереди.' : 'Сопоставляем публикации с профилем компании и подбираем источники.'}</Text><div className="indeterminate-track" aria-hidden="true"><span /></div><div className="job-meta"><span>Публикаций в запросе: {job?.parameters.max_events ?? '—'}</span><span>Время завершения зависит от обработки</span></div><Callout>Вы можете продолжить работу. Статус обновляется автоматически, готовые выводы появятся после завершения задания.</Callout><Button view="text" size={40} onClick={onSourceChoice}>Перейти к новостям <ArrowRightMIcon /></Button></Panel>}
    {job?.status === 'failed' && <Panel className="job-panel"><Callout tone="error" title="Ошибка обработки задания">Сервер не смог завершить анализ. Предыдущие готовые выводы остаются доступны.</Callout><Disclosure title="Технические подробности"><code>{job.error_code || 'analysis_failed'}</code><Text className="caption">Задание: {job.id}<br />Завершение: {dateLabel(job.finished_at)}</Text></Disclosure><Button view="accent" size={40} className="accent-button" onClick={prepare}>Повторить запуск</Button></Panel>}
    {noResults && <Panel><EmptyState icon={<MagnifierMIcon />} title="Подходящих выводов не найдено" actions={<><Button view="accent" size={40} className="accent-button" onClick={onSourceChoice}>Выбрать другие новости</Button><Button view="secondary" size={40} onClick={prepare}>Изменить параметры запуска</Button></>}>В последнем задании не найдено достаточных оснований для персонального анализа. Это допустимый результат обработки, а не ошибка.</EmptyState><JobTotals job={job} /></Panel>}
    {job?.status === 'completed' && !noResults && <Callout tone="positive" title="Анализ завершён"><span>Создано выводов: {job.summary.created ?? job.insight_ids.length}. Пропущено публикаций: {job.summary.skipped ?? '—'}.</span><Text className="caption">Завершение: {dateLabel(job.finished_at)}</Text></Callout>}
    {feed.loading ? <LoadingCards /> : feed.error ? <ErrorState error={feed.error} retry={feed.reload} /> : !page?.total ? !processing && !noResults && job?.status !== 'failed' && <Panel><EmptyState icon={<BarChartMIcon />} title="Пока нет готовых анализов" actions={<><Button view="accent" size={48} className="accent-button" onClick={prepare}>Подготовить аналитику</Button><Button view="text" size={40} onClick={onSourceChoice}>Выбрать новости самостоятельно</Button></>}>Запустите анализ последних новостей, чтобы получить выводы для вашей компании и роли.</EmptyState></Panel> : <>
      <div className="results-heading"><div><H level={2}>Готовые выводы</H><Text>Персональная подборка · По релевантности</Text></div><Badge>Всего: {page.total}</Badge></div>
      <div className="insight-list">{page.items.map((item) => <Panel key={item.id} className="insight-card"><div className="metadata"><span className="icon-text"><ClockMIcon />Анализ: {dateLabel(item.created_at)}</span><ModeBadge mode={item.generation_mode} />{item.is_demo && <Badge>Синтетический сценарий</Badge>}</div><div className="category-label"><span />Релевантность профилю: {percent(item.relevance_score)}% · Эвристика</div><H>{item.title}</H><Text className="summary-preview">{page.previews[item.id]?.interpretation || 'Краткий вывод недоступен. Откройте подробный анализ.'}</Text><div className="insight-footer"><div className="confidence-inline"><div><strong>Оценка уверенности: {percent(item.confidence)}%</strong><span>Эвристический показатель</span></div><ProgressBar value={percent(item.confidence)} size={4} view={item.confidence > 0.8 ? 'accent' : 'primary'} className="confidence-progress" /></div><Button href={`#/analysis/${item.id}`} view="accent" size={40} className="accent-button" rightAddons={<ArrowRightMIcon />}>Открыть анализ</Button></div></Panel>)}</div>
      <div className="pagination"><span className="caption">{offset + 1}–{offset + page.items.length} из {page.total} выводов</span><div className="actions"><Button view="secondary" size={32} disabled={!offset} onClick={() => { setOffset(Math.max(0, offset - 6)); window.scrollTo(0, 0); }}>Назад</Button><Button view="secondary" size={32} disabled={offset + page.limit >= page.total} onClick={() => { setOffset(offset + 6); window.scrollTo(0, 0); }}>Далее</Button></div></div>
      <Text className="muted">Уверенность и релевантность — эвристические оценки, не финансовая гарантия. Синтетические материалы отмечены отдельно.</Text>
    </>}
  </div>;
}
