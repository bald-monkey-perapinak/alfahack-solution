import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeftMIcon } from '@alfalab/icons-glyph/ArrowLeftMIcon';
import { ArrowRightMIcon } from '@alfalab/icons-glyph/ArrowRightMIcon';
import { CheckmarkMIcon } from '@alfalab/icons-glyph/CheckmarkMIcon';
import { ApiError, AnalyticsApi, errorMessage, isAborted } from '../api/client';
import type { GenerationMode, Insight, QuestionAnswer, Rating } from '../api/types';
import type { SourceTarget } from '../components/SourceModal';
import { ErrorState, InlineError } from '../components/ApiFeedback';
import { Badge, Button, Callout, Disclosure, H, Input, LoadingCards, Panel, ProgressBar, Spinner, Text, Textarea, fieldProps } from '../components/ui';
import { asRecord, dateLabel, displayValue, percent, roleLabel } from '../domain';
import { useResource } from '../hooks/useResource';
import { ModeBadge } from './AnalyticsPage';

export function DetailPage({ api, id, companyName, serverMode, source }: { api: AnalyticsApi; id: string; companyName: string; serverMode?: GenerationMode; source: (target: SourceTarget) => void }) {
  const numericId = Number(id);
  const resource = useResource((signal) => Number.isSafeInteger(numericId) && numericId > 0 ? api.insight(numericId, signal) : Promise.reject(new ApiError(404, 'insight_not_found')), [api, numericId]);
  if (resource.loading) return <LoadingCards />;
  if (resource.error) return <div className="page-stack"><Button view="text" size={32} href="#/analysis" leftAddons={<ArrowLeftMIcon />}>К аналитике</Button><ErrorState error={resource.error} retry={resource.reload} /></div>;
  return resource.data && <DetailContent key={resource.data.id} api={api} insight={resource.data} companyName={companyName} serverMode={serverMode} source={source} />;
}

function DetailContent({ api, insight, companyName, serverMode, source }: { api: AnalyticsApi; insight: Insight; companyName: string; serverMode?: GenerationMode; source: (target: SourceTarget) => void }) {
  const original = insight.evidence.find((item) => item.material_id === insight.primary_material_id);
  const bankEvidence = insight.evidence.filter((item) => item.section === 'bank_view');
  const snapshot = asRecord(asRecord(insight.company_context).profile);
  const observed = asRecord(snapshot.observed);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<QuestionAnswer | null>(null);
  const [questionError, setQuestionError] = useState<unknown>(null);
  const [questionValidation, setQuestionValidation] = useState('');
  const [questionBusy, setQuestionBusy] = useState(false);
  const [serverOffline, setServerOffline] = useState(false);
  const [vote, setVote] = useState<Rating | ''>('');
  const [comment, setComment] = useState('');
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState<unknown>(null);
  const [voteError, setVoteError] = useState(false);
  const questionRequest = useRef<AbortController | null>(null);
  const feedbackRequest = useRef<AbortController | null>(null);
  useEffect(() => () => { questionRequest.current?.abort(); feedbackRequest.current?.abort(); }, []);
  const allowQuestion = insight.payload.generation_mode === 'live' && serverMode === 'live' && !serverOffline;
  async function ask(event: FormEvent) {
    event.preventDefault(); if (questionBusy || !allowQuestion) return;
    if (question.trim().length < 3) { setQuestionValidation('Напишите вопрос — не менее 3 символов'); return; }
    const controller = new AbortController(); questionRequest.current = controller;
    setQuestionError(null); setQuestionValidation(''); setAnswer(null); setQuestionBusy(true);
    try {
      const result = await api.question(insight.id, question.trim(), controller.signal);
      if (!controller.signal.aborted) { setAnswer(result); setServerOffline(result.generation_mode === 'offline'); }
    } catch (cause) { if (!controller.signal.aborted && !isAborted(cause)) setQuestionError(cause); }
    finally { if (!controller.signal.aborted) setQuestionBusy(false); }
  }
  async function sendFeedback() {
    if (feedbackBusy) return;
    if (!vote) { setVoteError(true); return; }
    const controller = new AbortController(); feedbackRequest.current = controller;
    setFeedbackBusy(true); setFeedbackError(null); setFeedbackSaved(false);
    try { await api.feedback(insight.id, vote, comment, controller.signal); if (!controller.signal.aborted) setFeedbackSaved(true); }
    catch (cause) { if (!controller.signal.aborted && !isAborted(cause)) setFeedbackError(cause); }
    finally { if (!controller.signal.aborted) setFeedbackBusy(false); }
  }
  const confidence = percent(insight.confidence);
  const warnings = Array.isArray(insight.payload.warnings) ? insight.payload.warnings : [];
  const auditLabels: Record<string, string> = { plan: 'План обработки', 'event.extract': 'Извлечение факторов', 'factor.propagate': 'Оценка чувствительности профиля', 'connections.assess': 'Оценка связей из данных организаторов', 'event.rank': 'Расчёт релевантности', 'bank.retrieve': 'Поиск аналитики банка', 'bank.retry': 'Дополнительный поиск источников', 'insight.generate': 'Формирование вывода', 'insight.verify': 'Проверка результата', skip: 'Публикация пропущена' };
  return <div className="page-stack detail-page">
    <div className="detail-heading"><Button view="text" size={32} href="#/analysis" leftAddons={<ArrowLeftMIcon />}>К аналитике</Button><div className="metadata"><span>Анализ: {dateLabel(insight.created_at)}</span><ModeBadge mode={insight.payload.generation_mode} />{insight.payload.is_demo && <Badge>Синтетический сценарий</Badge>}</div><H level={1}>{insight.title}</H><Text className="context-line">{companyName} · {roleLabel(insight.target_role)} · Контекст на момент анализа</Text></div>
    <div className="detail-grid"><div className="stack detail-main">
      <Panel title="Факты события"><ul className="fact-list"><li><CheckmarkMIcon aria-hidden="true" /><Text className="rich-text">{insight.facts}</Text></li></ul><Button view="text" size={32} onClick={() => source({ id: insight.primary_material_id, quote: original?.quote })}>Проверить первоисточник ↗</Button></Panel>
      <Panel title="Почему это важно для вашей компании"><Text className="rich-text">{insight.relevance_reason}</Text><div className="exposure-grid"><div className="subcard"><span className="caption">Отрасль на момент анализа</span><strong>{displayValue(observed.okved_name)}</strong><Text>Применимость проверяется по фактическим операциям.</Text></div><div className="subcard"><span className="caption">Аналитическая роль</span><strong>{roleLabel(insight.target_role)}</strong><Text>Вывод подготовлен для этой роли.</Text></div></div></Panel>
      {insight.payload.connection_analysis && <Panel title="Связи компании в анализе"><Text>Проверено связанных компаний: {insight.payload.connection_analysis.examined_count}. С известным профилем: {insight.payload.connection_analysis.profiled_count}.</Text>{insight.payload.connection_analysis.top_paths.length ? <ul>{insight.payload.connection_analysis.top_paths.map((path) => <li key={path.organization_id}><strong>{path.label}</strong> · глубина {path.depth} · вес пути {percent(path.weight)}%<Text className="caption">{path.edges.map((edge) => edge.evidence).join(' → ')}</Text></li>)}</ul> : <Text>Значимые косвенные сигналы по доступным профилям не выявлены.</Text>}<Callout>{insight.payload.connection_analysis.note}{insight.payload.connection_analysis.truncated ? ' Достигнут лимит обхода графа.' : ''}</Callout></Panel>}
      <Panel title="Позиция банка">{insight.bank_view ? <>
        <Badge tone={bankEvidence.some((item) => item.published_at) ? 'positive' : 'neutral'}>{bankEvidence.some((item) => item.published_at) ? 'Найдена датированная аналитика' : 'Аналитический материал'}</Badge>
        <blockquote className="rich-text">{insight.bank_view}</blockquote>
        {bankEvidence.map((item) => <div className="bank-evidence" key={item.id}><Text className="caption">{dateLabel(item.published_at)}</Text><Button view="text" size={32} onClick={() => source({ id: item.material_id, quote: item.quote })}>{item.source_title} ↗</Button></div>)}
      </> : <><Badge>Без позиции</Badge><Callout>Подходящая датированная аналитика банка не найдена. Позиция банка не добавляется к выводу без источника.</Callout></>}</Panel>
      <Panel title="Персональная интерпретация"><Text className="rich-text">{insight.interpretation}</Text><Callout title="Ограничение анализа">Индексы чувствительности не являются прогнозом финансового ущерба. Последствия зависят от условий конкретных договоров и полноты данных.</Callout></Panel>
      <Panel title="Риски и возможности"><div className="risk-grid"><div className="risk-box"><H level={3}>Выявленные риски</H>{insight.risks.length ? <ul>{insight.risks.map((item, index) => <li key={index}>{item}</li>)}</ul> : <Text>Отдельные риски в результате не указаны.</Text>}</div><div className="opportunity-box"><H level={3}>Потенциальные возможности</H>{insight.opportunities.length ? <ul>{insight.opportunities.map((item, index) => <li key={index}>{item}</li>)}</ul> : <Text>На имеющихся данных отдельные возможности не выявлены.</Text>}</div></div></Panel>
      <Panel title="Рекомендуемые действия">{insight.suggested_actions.length ? <ol className="action-list">{[...insight.suggested_actions].sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999)).map((item, index) => <li key={index}><span className="step-number">{index + 1}</span><div><H level={3}>{item.rationale || item.label || 'Проверить применимость вывода'}</H></div></li>)}</ol> : <Text>Рекомендуемые действия в результате не указаны.</Text>}</Panel>
      <Panel className="audit-panel"><Disclosure title="Как подготовлен анализ"><Text>Фактически выполненные этапы обработки из серверного журнала, без внутренних инструкций модели.</Text>{insight.steps.length ? <ol className="audit-log">{insight.steps.map((step, index) => <li key={index}><strong>{auditLabels[step.tool] || step.tool}</strong>{step.at && <span> · {dateLabel(step.at)}</span>}{typeof asRecord(step.result).shock_count === 'number' && <span> · факторов: {String(asRecord(step.result).shock_count)}</span>}</li>)}</ol> : <Text>Журнал этапов не предоставлен.</Text>}</Disclosure></Panel>
    </div><aside className="stack detail-aside" aria-label="Источники и контекст анализа">
      <Panel title="Первоисточник"><Badge>Исходный материал</Badge><H level={3}>{original?.source_title || 'Исходная публикация'}</H><Text className="caption">Публикация: {dateLabel(original?.published_at)}</Text>{original?.quote && <blockquote>{original.quote}</blockquote>}<Button view="secondary" size={40} block onClick={() => source({ id: insight.primary_material_id, quote: original?.quote })}>Открыть первоисточник ↗</Button></Panel>
      <Panel title="Уверенность модели"><strong className="confidence-number">{confidence}<span>%</span></strong><ProgressBar value={confidence} size={8} view="accent" className="confidence-progress" /><Text className="caption">Эвристический показатель соответствия факторов новости и профиля организации. Не является финансовой гарантией или аудиторским заключением.</Text></Panel>
      <Panel title="Предупреждения и допущения">{warnings.length ? <ul className="plain-list">{warnings.map((item, index) => <li key={index}>{item}</li>)}</ul> : <Text className="caption">Дополнительные предупреждения не указаны.</Text>}</Panel>
      <Panel title="Контекст клиента"><dl className="properties"><div><dt>Компания</dt><dd>{companyName}</dd></div><div><dt>Отрасль при анализе</dt><dd>{displayValue(observed.okved_name)}</dd></div><div><dt>Регион при анализе</dt><dd>{displayValue(observed.region)}</dd></div><div><dt>Роль при анализе</dt><dd>{roleLabel(insight.target_role)}</dd></div></dl><Button view="text" size={32} href="#/profile">Посмотреть текущий профиль →</Button></Panel>
    </aside></div>
    <Panel title="Уточнить по этому анализу" className="question-panel">
      {!allowQuestion ? <><Callout title="Свободный диалог недоступен">{serverMode === undefined ? 'Не удалось подтвердить режим работы сервиса. Обновите статус сервиса перед отправкой вопроса.' : 'Показано существующее объяснение по анализу. В режиме без LLM произвольные вопросы не обрабатываются.'}</Callout><Input {...fieldProps} label="Ваш вопрос" disabled placeholder="Диалог недоступен в текущем режиме" /><div className="answer-box"><Badge>Существующее объяснение</Badge><Text className="rich-text">{insight.interpretation}</Text></div></> : <>
        <Text className="muted">Уточните вывод или попросите объяснить, на какие данные он опирается.</Text><form className="question-form" onSubmit={ask} noValidate><Input {...fieldProps} label="Ваш вопрос" placeholder="Какие условия договоров проверить в первую очередь?" value={question} maxLength={2000} disabled={questionBusy} error={questionValidation} fieldClassName={questionValidation ? undefined : fieldProps.fieldClassName} onChange={(event) => { setQuestion(event.target.value); setQuestionValidation(''); }} /><Button view="accent" size={48} type="submit" className="accent-button" loading={questionBusy} disabled={questionBusy} rightAddons={<ArrowRightMIcon />}>Задать вопрос</Button></form>
      </>}
      {questionBusy && <div className="answer-loading" role="status"><Spinner visible preset={16} />Подготавливаем ответ по источникам…</div>}
      {Boolean(questionError) && <Callout tone="error">{errorMessage(questionError)}</Callout>}
      {answer && <div className="answer-box" aria-live="polite"><ModeBadge mode={answer.generation_mode} /><Text className="rich-text">{answer.answer}</Text><div className="actions">{answer.sources.map((item, index) => <Button key={index} view="text" size={32} onClick={() => source({ id: item.material_id, quote: item.quote })}>{insight.evidence.find((evidence) => evidence.material_id === item.material_id)?.source_title || `Источник #${item.material_id}`} ↗</Button>)}</div></div>}
    </Panel>
    <Panel title="Оценка полезности"><Text>Был ли этот анализ полезен для принятия решений?</Text><div className="feedback-options">{([{ id: 'useful', label: 'Полезно' }, { id: 'not_useful', label: 'Не полезно' }, { id: 'already_known', label: 'Уже известно' }] as const).map((item) => <Button key={item.id} view="secondary" size={40} disabled={feedbackBusy} className={vote === item.id ? 'choice-button selected' : 'choice-button'} aria-pressed={vote === item.id} onClick={() => { setVote(item.id); setFeedbackSaved(false); setVoteError(false); }}>{item.label}</Button>)}</div><Textarea {...fieldProps} id="feedback-comment" aria-label="Дополнительный комментарий (необязательно)" label="Дополнительный комментарий (необязательно)" value={comment} disabled={feedbackBusy} minRows={2} maxRows={5} autosize maxLength={2000} onChange={(event) => { setComment(event.target.value); setFeedbackSaved(false); }} />{voteError && <Text className="error-text">Выберите один из трёх вариантов оценки.</Text>}{Boolean(feedbackError) && <InlineError error={feedbackError} />}{feedbackSaved ? <Callout tone="positive">Спасибо! Ваша оценка сохранена на сервере.</Callout> : <Button view="accent" size={40} className="accent-button" loading={feedbackBusy} disabled={feedbackBusy} onClick={() => void sendFeedback()}>Отправить</Button>}</Panel>
  </div>;
}
