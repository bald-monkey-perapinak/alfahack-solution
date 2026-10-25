import { ExclamationCircleMIcon } from '@alfalab/icons-glyph/ExclamationCircleMIcon';
import { ApiError, errorMessage } from '../api/client';
import { Button, Callout, EmptyState, Panel, Text } from './ui';

export function ErrorState({ error, retry, title }: { error: unknown; retry?: () => void; title?: string }) {
  return <Panel><EmptyState icon={<ExclamationCircleMIcon />} title={title || (error instanceof ApiError && error.status === 404 ? 'Данные не найдены' : 'Не удалось загрузить данные')} actions={retry && <Button view="accent" size={40} className="accent-button" onClick={retry}>Попробовать снова</Button>}>{errorMessage(error)}</EmptyState></Panel>;
}
export function InlineError({ error, retry }: { error: unknown; retry?: () => void }) {
  return <Callout tone="error"><span>{errorMessage(error)}</span>{retry && <Button view="text" size={32} onClick={retry}>Повторить</Button>}{error instanceof ApiError && error.requestId && <Text className="caption">Код обращения: {error.requestId}</Text>}</Callout>;
}
