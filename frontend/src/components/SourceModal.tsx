import { useState } from 'react';
import { CopyMIcon } from '@alfalab/icons-glyph/CopyMIcon';
import { AnalyticsApi } from '../api/client';
import { dateLabel, quoteSegments, safeExternalUrl } from '../domain';
import { useResource } from '../hooks/useResource';
import { ErrorState } from './ApiFeedback';
import { Badge, Button, Callout, H, IconButton, LoadingCards, Modal, Text } from './ui';

export type SourceTarget = { id: number; quote?: string };
export function SourceModal({ api, target, close }: { api: AnalyticsApi; target: SourceTarget; close: () => void }) {
  const resource = useResource((signal) => api.material(target.id, signal), [api, target.id]);
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');
  const material = resource.data;
  const external = safeExternalUrl(material?.source_ref, material?.is_demo);
  const quote = target.quote?.trim();
  async function copy() {
    if (!quote) return;
    try { await navigator.clipboard.writeText(quote); setCopyState('copied'); }
    catch { setCopyState('error'); }
  }
  return <Modal open onClose={close} size={800} hasCloser className="source-modal"><Modal.Header title="Просмотр источника" /><Modal.Content>
    {resource.loading ? <LoadingCards /> : resource.error ? <ErrorState error={resource.error} retry={resource.reload} /> : material && <div className="stack">
      <div className="metadata"><Badge>{material.material_type === 'bank_analytics' ? 'Аналитика банка' : 'Новость'}</Badge><span>{dateLabel(material.published_at)}</span></div><H>{material.title}</H><Text className="muted">{material.source_name}</Text>
      {material.is_demo && <Callout title="Демонстрационный источник данных">Синтетический материал. Он не описывает реальное событие.</Callout>}
      {quote && !material.body.includes(quote) && <Callout>Цитата не найдена в текущей версии полного текста. Сверьте исходный материал.</Callout>}
      <div className="source-body"><Text className="rich-text">{quoteSegments(material.body, quote).map((fragment, index) => fragment.highlighted ? <mark key={index}>{fragment.text}</mark> : <span key={index}>{fragment.text}</span>)}</Text></div>
      {quote && <div className="source-quote-footer"><span className="caption">Фрагмент, использованный в анализе</span><IconButton view="transparent" size={32} icon={CopyMIcon} aria-label="Скопировать цитату" onClick={() => void copy()} /></div>}
      {copyState === 'copied' && <Text className="positive-text">Цитата скопирована</Text>}{copyState === 'error' && <Text className="error-text">Не удалось скопировать. Выделите цитату и скопируйте вручную.</Text>}
      {external ? <Button href={external} target="_blank" rel="noopener noreferrer" view="secondary" size={40}>Открыть оригинал ↗</Button> : <Text className="caption">{material.is_demo ? 'Внешняя ссылка не открывается для синтетического материала.' : 'Материал доступен в корпусе источников.'}</Text>}
    </div>}
  </Modal.Content><Modal.Footer><Button view="secondary" size={40} onClick={close}>Закрыть</Button></Modal.Footer></Modal>;
}
