import { useId, useState, type ReactNode } from 'react';
import { Typography } from '@alfalab/core-components/typography';
import { Status } from '@alfalab/core-components/status';
import { Collapse } from '@alfalab/core-components/collapse';
import { Button } from '@alfalab/core-components/button';
import { Skeleton } from '@alfalab/core-components/skeleton';
import { ChevronDownMIcon } from '@alfalab/icons-glyph/ChevronDownMIcon';
export { Typography, Button, Collapse };
export { Input } from '@alfalab/core-components/input';
export { PasswordInput } from '@alfalab/core-components/password-input';
export { Select } from '@alfalab/core-components/select';
export { Checkbox } from '@alfalab/core-components/checkbox';
export { Modal } from '@alfalab/core-components/modal';
export { IconButton } from '@alfalab/core-components/icon-button';
export { Circle } from '@alfalab/core-components/icon-view/circle';
export { Spinner } from '@alfalab/core-components/spinner';
export { ProgressBar } from '@alfalab/core-components/progress-bar';
export { Textarea } from '@alfalab/core-components/textarea';

export const fieldProps = { size: 48 as const, labelView: 'outer' as const, block: true, fieldClassName: 'control-surface' };
export function H({ children, level = 2, className = '', id }: { children: ReactNode; level?: 1 | 2 | 3; className?: string; id?: string }) {
  return <Typography.Title tag={`h${level}`} font="system" weight="semibold" className={`heading heading-${level} ${className}`} id={id}>{children}</Typography.Title>;
}
export function Text({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <Typography.Text tag="p" view="primary-small" className={`copy ${className}`}>{children}</Typography.Text>;
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'positive' | 'blue' }) {
  return <Status size={20} shape="rounded" uppercase={false} view="muted-alt" color={tone === 'positive' ? 'green' : tone === 'accent' ? 'red' : tone === 'blue' ? 'blue' : 'grey'} className={`meta-badge meta-badge--${tone}`}>{children}</Status>;
}
export function Panel({ children, title, action, className = '', id }: { children: ReactNode; title?: string; action?: ReactNode; className?: string; id?: string }) {
  const generated = useId();
  return <section className={`panel ${className}`} aria-labelledby={title ? id || generated : undefined}>
    {title && <div className="panel-heading"><H id={id || generated}>{title}</H>{action}</div>}{children}
  </section>;
}
export function Callout({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'error' | 'positive'; title?: string }) {
  return <div className={`callout callout--${tone}`} role={tone === 'error' ? 'alert' : undefined}>{title && <strong>{title}</strong>}<div className="callout-content">{children}</div></div>;
}
export function Disclosure({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return <div className="disclosure"><Button view="text" size={40} className="disclosure-trigger" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
    <span>{title}</span><ChevronDownMIcon aria-hidden="true" className={open ? 'chevron expanded' : 'chevron'} />
  </Button><Collapse expanded={open} id={id}><div className="disclosure-body" inert={!open}>{children}</div></Collapse></div>;
}
export function EmptyState({ icon, title, children, actions }: { icon: ReactNode; title: string; children: ReactNode; actions?: ReactNode }) {
  return <div className="empty-state"><div className="empty-state-icon" aria-hidden="true">{icon}</div><H>{title}</H><Text>{children}</Text>{actions && <div className="empty-state-actions">{actions}</div>}</div>;
}
export function LoadingCards() {
  return <div className="stack" role="status" aria-label="Загрузка содержимого" aria-busy="true">{[0, 1, 2].map((item) => <Panel key={item} className="skeleton-panel">
    <Skeleton visible animate style={{ height: 14, width: '36%' }} /><Skeleton visible animate style={{ height: 25, width: '76%' }} /><Skeleton visible animate style={{ height: 14, width: '96%' }} /><Skeleton visible animate style={{ height: 14, width: '60%' }} />
  </Panel>)}</div>;
}
