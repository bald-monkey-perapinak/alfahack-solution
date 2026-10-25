import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Tabs, Tab } from '@alfalab/core-components/tabs';
import { ArrowRightMIcon } from '@alfalab/icons-glyph/ArrowRightMIcon';
import { CheckmarkMIcon } from '@alfalab/icons-glyph/CheckmarkMIcon';
import { MailMIcon } from '@alfalab/icons-glyph/MailMIcon';
import { UserMIcon } from '@alfalab/icons-glyph/UserMIcon';
import { Button, Callout, Circle, H, Input, PasswordInput, Select, Spinner, Text, fieldProps } from '../components/ui';
import { AnalyticsApi, errorMessage, isAborted, validationErrors } from '../api/client';
import type { Organization } from '../api/types';
import { validateEntry } from '../domain';
import { useResource } from '../hooks/useResource';

export type EntryValues = { name: string; email: string; password: string; role: string; companyId: string };
export function EntryPage({ register, api, onEnter, info, sessionNotice }: {
  register: boolean; api: AnalyticsApi; onEnter: (values: EntryValues, register: boolean, signal: AbortSignal) => Promise<void>;
  info: (message: string) => void; sessionNotice: string;
}) {
  const [values, setValues] = useState<EntryValues>({ name: '', email: '', password: '', role: '', companyId: '' });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [catalog, setCatalog] = useState<Organization[]>([]);
  const [chosen, setChosen] = useState<Organization | null>(null);
  const [catalogError, setCatalogError] = useState<unknown>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const authRequest = useRef<AbortController | null>(null);
  const roles = useResource((signal) => register ? api.roles(signal) : Promise.resolve({ items: [] }), [api, register]);
  useEffect(() => () => authRequest.current?.abort(), []);
  useEffect(() => {
    if (!register) return;
    const controller = new AbortController();
    setCatalogLoading(true); setCatalogError(null);
    const timer = setTimeout(() => {
      api.organizations(query, 0, controller.signal).then((page) => {
        if (!controller.signal.aborted) { setCatalog(page.items); setCatalogLoading(false); }
      }).catch((cause: unknown) => {
        if (!controller.signal.aborted && !isAborted(cause)) { setCatalogError(cause); setCatalogLoading(false); setCatalog([]); }
      });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, register, query, catalogAttempt]);
  function change(key: keyof EntryValues, value: string) {
    setValues((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => ({ ...previous, [key]: '' })); setError('');
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const next = validateEntry(values, register); setErrors(next);
    if (Object.keys(next).length) {
      const field = event.currentTarget.elements.namedItem(Object.keys(next)[0]);
      if (field instanceof HTMLElement) field.focus();
      return;
    }
    const controller = new AbortController(); authRequest.current = controller;
    setBusy(true); setError('');
    try { await onEnter(values, register, controller.signal); }
    catch (cause) { if (!controller.signal.aborted) { setError(errorMessage(cause)); setErrors(validationErrors(cause)); } }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  const available = chosen && !catalog.some((item) => item.id === chosen.id) ? [chosen, ...catalog] : catalog;
  const companyOptions = available.map((company) => ({ key: String(company.id), content: <span className="company-option"><strong>{company.name}</strong><small>{company.synthetic_u || `ID: ${company.id}`} · {company.industry || 'Отрасль не указана'} · {company.region || 'Регион не указан'}</small></span> }));
  return <div className="entry-page">
    <header className="entry-heading"><a href="#/login" className="brand"><span className="brand-tile">А</span><span>Альфа-Бизнес<small>Новости и аналитика</small></span></a><span className="caption">Рабочий кабинет</span></header>
    <main className="entry-main"><div className="entry-card">
      <section className="entry-story" aria-labelledby="entry-story-title">
        <div className="entry-brand"><span className="brand-tile">А</span><div>Альфа-Бизнес<small>ИНТЕЛЛЕКТ & МОНИТОРИНГ</small></div></div>
        <div className="entry-story-label">ДЛЯ ВАШЕГО БИЗНЕСА</div>
        <H level={2} id="entry-story-title">Персональная аналитика для вашего бизнеса</H>
        <Text>Новости, контекст компании и аналитические выводы в одном рабочем пространстве.</Text>
        <ul className="entry-benefits">{['Персональная калибровка выводов под профиль компании', 'Анализ фактов и сопоставление с позицией банка', 'Прозрачные эвристические оценки и проверяемые источники'].map((item) => <li key={item}><CheckmarkMIcon aria-hidden="true" />{item}</li>)}</ul>
        <div className="entry-story-footer"><span className="demo-dot" /><Text>Сервис работает с обезличенным каталогом компаний. Синтетические публикации и анализ по правилам отмечены в интерфейсе.</Text></div>
      </section>
      <section className="entry-form-panel" aria-labelledby="entry-title">
        <div className="entry-form-heading"><Circle size={56} backgroundColor="#F3F4F6"><UserMIcon aria-hidden="true" /></Circle><H level={1} id="entry-title">{register ? 'Регистрация в кабинете' : 'Вход в кабинет'}</H><Text>{register ? 'Создайте профиль для персональной аналитики' : 'Ваш рабочий кабинет новостей и аналитики'}</Text></div>
        <Tabs selectedId={register ? 'register' : 'login'} onChange={(_, { selectedId }) => { window.location.hash = selectedId === 'register' ? '/register' : '/login'; }} view="secondary" tagView="filled" tagShape="rounded" size="s" className="entry-tabs"><Tab id="login" title="Вход" /><Tab id="register" title="Регистрация" /></Tabs>
        <Button view="accent" size={48} block className="accent-button bank-button" onClick={() => info('Вход через Альфа-Бизнес пока недоступен. Используйте e-mail и пароль вашего аккаунта в этом сервисе.')}><span className="button-inline"><span className="bank-letter">А</span>{register ? 'Регистрация через Альфа-Бизнес' : 'Войти через Альфа-Бизнес'}</span></Button>
        <div className="bank-soon"><span />Скоро · Банковская интеграция в разработке</div>
        <div className="divider-label">{register ? 'ИЛИ ЗАПОЛНИТЕ ДАННЫЕ ВРУЧНУЮ' : 'ИЛИ ЧЕРЕЗ РАБОЧИЙ E-MAIL'}</div>
        {sessionNotice && <Callout>{sessionNotice}</Callout>}
        <form noValidate onSubmit={submit} className="entry-fields">
          {register && <Input {...fieldProps} name="name" label="Имя и фамилия" placeholder="Имя Фамилия" maxLength={255} value={values.name} error={errors.name} fieldClassName={errors.name ? undefined : fieldProps.fieldClassName} onChange={(event) => change('name', event.target.value)} autoComplete="name" disabled={busy} />}
          <Input {...fieldProps} name="email" label="Рабочий e-mail" type="email" maxLength={254} placeholder="name@company.ru" leftAddons={<MailMIcon aria-hidden="true" />} value={values.email} error={errors.email} fieldClassName={errors.email ? undefined : fieldProps.fieldClassName} onChange={(event) => change('email', event.target.value)} autoComplete="username" disabled={busy} />
          {register && <>
            <Select name="companyId" size={48} block labelView="outer" label="Компания (выбор из каталога)" placeholder="Найдите вашу компанию" options={companyOptions} selected={values.companyId || null} showSearch optionsListWidth="field" disabled={busy}
              searchProps={{ value: query, onChange: setQuery, filterFn: () => true, componentProps: { placeholder: 'Название, идентификатор или отрасль' } }}
              valueRenderer={() => chosen?.name || ''}
              optionsListProps={{ emptyPlaceholder: catalogLoading ? 'Загрузка каталога…' : catalogError ? 'Не удалось загрузить каталог' : 'Компании не найдены' }}
              fieldProps={{ fieldClassName: errors.companyId ? undefined : fieldProps.fieldClassName }} error={errors.companyId}
              onChange={({ selected }) => { setChosen(available.find((item) => String(item.id) === selected?.key) || null); change('companyId', selected?.key || ''); setQuery(''); }} />
            {catalogLoading && <span className="field-caption"><Spinner visible preset={16} /> Загрузка каталога</span>}
            {catalogError ? <Callout tone="error">{errorMessage(catalogError)} <Button view="text" size={32} onClick={() => setCatalogAttempt((value) => value + 1)}>Повторить</Button></Callout> : <span className="field-caption">Поиск по серверному каталогу. Выбор компании не подтверждает полномочия.</span>}
            <Select size={48} block name="role" labelView="outer" label="Аналитическая роль" placeholder={roles.loading ? 'Загрузка ролей…' : 'Выберите вашу роль'} options={(roles.data?.items || []).map((item) => ({ key: item.id, content: item.name }))} selected={values.role || null} error={errors.role} disabled={busy || roles.loading || Boolean(roles.error)} fieldProps={{ fieldClassName: errors.role ? undefined : fieldProps.fieldClassName }} onChange={({ selected }) => change('role', selected?.key || '')} />
            {Boolean(roles.error) && <Callout tone="error">{errorMessage(roles.error)} <Button view="text" size={32} onClick={roles.reload}>Повторить загрузку ролей</Button></Callout>}
          </>}
          <PasswordInput {...fieldProps} name="password" label="Пароль" maxLength={128} value={values.password} error={errors.password} fieldClassName={errors.password ? undefined : fieldProps.fieldClassName} onChange={(event) => change('password', event.target.value)} autoComplete={register ? 'new-password' : 'current-password'} disabled={busy} hint={register ? 'От 10 до 128 символов' : undefined} passwordHint={{ hidden: 'Показать пароль', visible: 'Скрыть пароль' }} />
          {error && <Callout tone="error">{error}</Callout>}
          <Button view="primary" size={48} block type="submit" loading={busy} disabled={busy} className="dark-button" rightAddons={<ArrowRightMIcon aria-hidden="true" />}>{register ? 'Создать аккаунт' : 'Войти в систему'}</Button>
        </form>
        <div className="entry-switch">{register ? 'Уже зарегистрированы?' : 'Нет аккаунта?'} <Button href={register ? '#/login' : '#/register'} view="text" size={32}>{register ? 'Войти' : 'Зарегистрироваться'}</Button></div>
        <Text className="entry-disclaimer">{register ? 'Используйте рабочий аккаунт и компанию из доступного каталога.' : 'После обновления страницы потребуется повторный вход.'}</Text>
      </section>
    </div></main>
    <footer className="entry-footer"><span>Альфа-Бизнес · Новости и аналитика</span><span>Персональный рабочий кабинет</span></footer>
  </div>;
}
