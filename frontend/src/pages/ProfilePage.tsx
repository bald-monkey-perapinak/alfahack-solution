import { useEffect, useRef, useState, type FormEvent } from 'react';
import { OfficeMIcon } from '@alfalab/icons-glyph/OfficeMIcon';
import { Badge, Button, Callout, Circle, H, Input, LoadingCards, Panel, Select, Text, fieldProps } from '../components/ui';
import { ErrorState, InlineError } from '../components/ApiFeedback';
import { AnalyticsApi, errorMessage, isAborted, validationErrors } from '../api/client';
import type { OrganizationContext, User } from '../api/types';
import { displayValue, initials, type Role } from '../domain';
import { useResource } from '../hooks/useResource';

export function ProfilePage({ api, user, company, companyError, companyLoading, reloadCompany, savedUser, logout, logoutBusy, logoutError }: {
  api: AnalyticsApi; user: User; company: OrganizationContext | null; companyError: unknown; companyLoading: boolean;
  reloadCompany: () => void; savedUser: (user: User) => void; logout: () => void; logoutBusy: boolean; logoutError: unknown;
}) {
  const [name, setName] = useState(user.name);
  const [role, setRole] = useState<Role>(user.role);
  const [organizationId, setOrganizationId] = useState(String(user.org_id));
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  useEffect(() => { const timer = setTimeout(() => setSearch(query.trim()), 250); return () => clearTimeout(timer); }, [query]);
  const organizations = useResource((signal) => api.organizations(search, 0, signal), [api, search]);
  const [error, setError] = useState('');
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const saveRequest = useRef<AbortController | null>(null);
  useEffect(() => () => saveRequest.current?.abort(), []);
  const roles = useResource((signal) => api.roles(signal), [api]);
  const partners = useResource((signal) => api.counterparties(signal), [api, user.org_id]);
  const org = company?.organization;
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    if (!name.trim()) { setError('Укажите имя и фамилию'); return; }
    const controller = new AbortController(); saveRequest.current = controller;
    setBusy(true); setSaveError(null); setSaved(false);
    try {
      const next = await api.updateMe({ name: name.trim(), role, organization_id: Number(organizationId) }, controller.signal);
      if (!controller.signal.aborted) { savedUser(next); setName(next.name); setRole(next.role); setSaved(true); }
    } catch (cause) { if (!isAborted(cause) && !controller.signal.aborted) { setSaveError(cause); setError(validationErrors(cause).name || ''); } }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  const relationLabels = { supplier: 'Поставщик', buyer: 'Покупатель', partner: 'Партнёр', other: 'Другая связь', payment: 'Платёжная связь', group: 'Группа компаний', shared_person: 'Общее лицо' };
  return <div className="page-stack"><div className="page-heading"><div><H level={1}>Профиль и компания</H><Text>Ваши данные и контекст персональной аналитики</Text></div></div>
    <div className="profile-grid"><Panel title="Информация профиля"><div className="profile-intro"><Circle size={64} backgroundColor="#F3F4F6" text={initials(name)} /><div><strong>{user.name}</strong><span className="caption">Профиль пользователя</span></div></div>
      <form className="stack" onSubmit={submit} noValidate>
        <Input {...fieldProps} name="profile-name" label="Имя и фамилия" value={name} maxLength={255} error={error} disabled={busy || logoutBusy} fieldClassName={error ? undefined : fieldProps.fieldClassName} onChange={(event) => { setName(event.target.value); setError(''); setSaved(false); }} />
        <Select size={48} block labelView="outer" label="Аналитическая роль" options={(roles.data?.items || []).map((item) => ({ key: item.id, content: item.name }))} selected={role} disabled={busy || logoutBusy || roles.loading || Boolean(roles.error)} fieldProps={{ fieldClassName: 'control-surface' }} onChange={({ selected }) => { setRole(selected?.key as Role || user.role); setSaved(false); }} />
        {Boolean(roles.error) && <InlineError error={roles.error} retry={roles.reload} />}
        <Input {...fieldProps} label="Поиск компании из набора организаторов" value={query} maxLength={100} placeholder="U_…, отрасль или регион" onChange={(event) => setQuery(event.target.value)} />
        <Select size={48} block labelView="outer" label="Компания для анализа" selected={organizationId} disabled={busy || organizations.loading} options={[
          ...(!(organizations.data?.items || []).some((item) => String(item.id) === organizationId) ? [{ key: organizationId, content: organizationId === String(user.org_id) ? (org?.name || org?.synthetic_u || 'Текущая компания') : `Компания #${organizationId}` }] : []),
          ...(organizations.data?.items || []).map((item) => ({ key: String(item.id), content: `${item.synthetic_u || item.name} · ${item.industry || 'Отрасль неизвестна'} · ${item.region || 'Регион неизвестен'}` }))
        ]} fieldProps={{ fieldClassName: 'control-surface' }} onChange={({ selected }) => { setOrganizationId(String(selected?.key || user.org_id)); setSaved(false); }} />
        {Boolean(organizations.error) && <InlineError error={organizations.error} retry={organizations.reload} />}
        {company?.data_mode === 'organizers' && company.data_origin !== 'organizers' && <Callout>Выберите компанию U_… и сохраните профиль, чтобы анализ использовал данные организаторов.</Callout>}
        <Text className="caption">Компании обезличены организаторами. Названия и ИНН в этом наборе отсутствуют.</Text>
        <Input {...fieldProps} label="Рабочий e-mail" value={user.email} readOnly fieldClassName="readonly-surface" hint="E-mail доступен только для чтения" />
        {Boolean(saveError) && <Callout tone="error">{errorMessage(saveError)}</Callout>}
        {saved && <Callout tone="positive">Изменения сохранены на сервере.{role !== user.role ? ' Лента будет обновлена для вашей роли.' : ''}</Callout>}
        {Boolean(logoutError) && <InlineError error={logoutError} />}
        <div className="actions profile-actions"><Button view="accent" size={40} className="accent-button" type="submit" loading={busy} disabled={busy || logoutBusy || Boolean(roles.error)}>Сохранить изменения</Button><Button view="text" size={40} onClick={logout} loading={logoutBusy} disabled={busy || logoutBusy}>Выйти из аккаунта</Button></div>
      </form>
    </Panel>
    {companyLoading ? <LoadingCards /> : companyError ? <ErrorState error={companyError} retry={reloadCompany} /> : org && <Panel title="Компания">
      <div className="company-title"><Circle size={40} backgroundColor="#F3F4F6"><OfficeMIcon /></Circle><div><H level={3}>{org.name || org.synthetic_u || `Компания #${org.id}`}</H><span className="caption">{org.synthetic_u || `ID: ${org.id}`}</span></div></div>
      <Badge>{company?.data_origin === 'organizers' ? 'Данные организаторов' : 'Демонстрационный профиль'}</Badge><dl className="properties"><div><dt>Отрасль</dt><dd>{displayValue(org.industry)}</dd></div><div><dt>ОКВЭД</dt><dd>{displayValue(org.okved_code)}</dd></div><div><dt>Регион</dt><dd>{displayValue(org.region)}</dd></div><div><dt>Город</dt><dd>{displayValue(org.city)}</dd></div></dl>
      <div className="company-flags">{([['Кредитный продукт', org.has_loans], ['Лизинг', org.has_leasing], ['Депозиты', org.has_deposits], ['Гарантии', org.has_guarantees], ['Факторинг', org.has_factoring], ['Внешнеэкономическая деятельность', org.has_foreign_trade]] as const).map(([label, value]) => <div className="flag-row" key={label}><span>{label}</span><strong>{value === null || value === undefined ? 'Не указано' : value ? 'Есть' : 'Нет'}</strong></div>)}</div>
      {org.foreign_trade_countries?.length > 0 && <Text className="caption">Страны ВЭД: {org.foreign_trade_countries.join(', ')}</Text>}
      <Callout>Признаки компании используются для контекста анализа. Наличие продукта не раскрывает условия конкретного договора.</Callout>
    </Panel>}</div>
    {partners.loading ? <LoadingCards /> : partners.error ? <ErrorState title="Не удалось загрузить контрагентов" error={partners.error} retry={partners.reload} /> : <Panel title="Контрагенты" action={<Badge>Только чтение</Badge>}><Text className="muted">{partners.data?.note || 'Связи из профиля компании.'}</Text>{!partners.data?.items.length ? <div className="inline-empty"><OfficeMIcon /><H level={3}>Связанные контрагенты не указаны</H><Text>В профиле компании пока нет данных о связях.</Text></div> : <div className="counterparty-list">{partners.data.items.map((item) => <div className="counterparty" key={item.id}><Circle size={40} backgroundColor="#F3F4F6"><OfficeMIcon /></Circle><div><strong>{item.counterparty_name}</strong><span>{item.evidence}{item.has_profile === false ? ' Профиль этой компании в наборе отсутствует.' : ''}</span></div><Badge>{relationLabels[item.relation_type] || 'Другая связь'}</Badge></div>)}</div>}</Panel>}
  </div>;
}
