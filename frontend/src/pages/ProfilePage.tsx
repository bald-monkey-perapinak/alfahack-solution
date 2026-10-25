import { useState, type FormEvent } from 'react';
import { Button } from '@alfalab/core-components/button';
import { IconButton } from '@alfalab/core-components/icon-button';
import { Circle } from '@alfalab/core-components/icon-view/circle';
import { Input } from '@alfalab/core-components/input';
import { Toast } from '@alfalab/core-components/toast';
import { Typography } from '@alfalab/core-components/typography';
import { CrossMIcon } from '@alfalab/icons-glyph/CrossMIcon';
import { OfficeMIcon } from '@alfalab/icons-glyph/OfficeMIcon';
import { CarMIcon } from '@alfalab/icons-glyph/CarMIcon';
import { PlusSIcon } from '@alfalab/icons-glyph/PlusSIcon';
import { ShopMIcon } from '@alfalab/icons-glyph/ShopMIcon';
import { demoCounterparties, demoProfile } from '../mocks/profile';
import { COUNTERPARTIES_STORAGE_KEY, PROFILE_STORAGE_KEY, getInitials, isCounterpartyList,
  isUserProfile, normalizeProfile, prepareCounterparty, readStoredValue, validateProfile } from '../lib/profile';
import type { Counterparty, ProfileErrors, UserProfile } from '../types/profile';
import './profile.css';

const kindLabels: Record<Counterparty['kind'], string> = {
  supplier: 'Поставщик', logistics: 'Логистика', buyer: 'Покупатель', other: 'Контрагент',
};
const kindIcons = { supplier: OfficeMIcon, logistics: CarMIcon, buyer: ShopMIcon, other: OfficeMIcon };

export function ProfilePage({ onSignOut }: { onSignOut: () => void }) {
  const [savedProfile, setSavedProfile] = useState(() => readStoredValue(PROFILE_STORAGE_KEY, demoProfile, isUserProfile));
  const [profile, setProfile] = useState(savedProfile);
  const [errors, setErrors] = useState<ProfileErrors>({});
  const [counterparties, setCounterparties] = useState(() => readStoredValue(COUNTERPARTIES_STORAGE_KEY, demoCounterparties, isCounterpartyList));
  const [query, setQuery] = useState('');
  const [queryError, setQueryError] = useState('');
  const [notice, setNotice] = useState('');
  const [removed, setRemoved] = useState<{ entry: Counterparty; index: number } | null>(null);
  const dirty = JSON.stringify(normalizeProfile(profile)) !== JSON.stringify(savedProfile);

  function changeField<K extends keyof UserProfile>(field: K, value: UserProfile[K]) {
    setProfile((previous) => ({ ...previous, [field]: value }));
    setErrors((previous) => ({ ...previous, [field]: undefined }));
  }

  function persist(key: string, value: unknown): boolean {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch {
      setRemoved(null);
      setNotice('Не удалось сохранить данные. Проверьте доступ к хранилищу браузера.');
      return false;
    }
  }

  function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = normalizeProfile(profile);
    const nextErrors = validateProfile(normalized);
    setErrors(nextErrors);
    const firstInvalid = Object.keys(nextErrors)[0];
    if (firstInvalid) {
      const field = event.currentTarget.elements.namedItem(firstInvalid);
      if (field instanceof HTMLElement) field.focus();
      return;
    }
    if (!persist(PROFILE_STORAGE_KEY, normalized)) return;
    setProfile(normalized);
    setSavedProfile(normalized);
    setRemoved(null);
    setNotice('Изменения сохранены в этом браузере');
  }

  function addCounterparty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = prepareCounterparty(query, counterparties);
    if (result.error !== undefined) { setQueryError(result.error); return; }
    const next = [...counterparties, { ...result.entry, id: crypto.randomUUID() }];
    if (!persist(COUNTERPARTIES_STORAGE_KEY, next)) return;
    setCounterparties(next);
    setQuery('');
    setQueryError('');
    setRemoved(null);
    setNotice('Контрагент добавлен в этом браузере');
  }

  function removeCounterparty(entry: Counterparty, index: number) {
    const next = counterparties.filter((item) => item.id !== entry.id);
    if (!persist(COUNTERPARTIES_STORAGE_KEY, next)) return;
    setCounterparties(next);
    setRemoved({ entry, index });
    setNotice('Контрагент удалён из списка');
  }

  function undoRemove() {
    if (!removed) return;
    const next = [...counterparties];
    next.splice(removed.index, 0, removed.entry);
    if (!persist(COUNTERPARTIES_STORAGE_KEY, next)) return;
    setCounterparties(next);
    setRemoved(null);
    setNotice('Контрагент восстановлен');
  }

  return (
    <main className="workspace profile-workspace">
      <div className="profile-page-heading">
        <Button view="text" size={32} className="profile-sign-out" onClick={onSignOut}>Выйти из демо</Button>
        <Typography.Title tag="h1" font="system" weight="semibold" className="profile-page-title">Личный кабинет</Typography.Title>
        <Typography.Text tag="p" view="primary-small" className="profile-page-description">Ваш профиль и компании, которые важны для бизнеса</Typography.Text>
      </div>

      <section className="profile-panel" aria-labelledby="profile-information-title">
        <form onSubmit={saveProfile} noValidate>
          <div className="profile-panel-heading">
            <div>
              <Typography.Title tag="h2" font="system" weight="semibold" className="profile-panel-title" id="profile-information-title">Информация профиля</Typography.Title>
              <Typography.Text tag="p" view="primary-small" className="profile-panel-description">Управление персональными данными сотрудника и организации</Typography.Text>
            </div>
            <Button type="submit" view="accent" size={40} disabled={!dirty} className="profile-save-button">Сохранить изменения</Button>
          </div>

          <div className="profile-identity">
            <Circle size={64} backgroundColor="#F3F4F6" className="profile-avatar" text={<span aria-hidden="true">{getInitials(profile.fullName)}</span>} />
            <div className="profile-identity-text">
              <Typography.Text tag="p" view="primary-medium" weight="medium" className="profile-identity-name">{profile.fullName.trim() || 'Фамилия и имя'}</Typography.Text>
              <Typography.Text tag="p" view="primary-small" className="profile-identity-role">{profile.role}{profile.role === 'Финансовый директор' ? ' (CFO)' : ''}</Typography.Text>
            </div>
          </div>

          <div className="profile-fields">
            <Input id="profile-full-name" name="fullName" label="ФИО" labelView="outer" size={48} block
              value={profile.fullName} onChange={(event) => changeField('fullName', event.target.value)}
              error={errors.fullName} fieldClassName={errors.fullName ? undefined : 'profile-control'} autoComplete="name" maxLength={160} />
            <Input id="profile-company" name="company" label="Компания" labelView="outer" size={48} block
              value={profile.company} onChange={(event) => changeField('company', event.target.value)}
              error={errors.company} fieldClassName={errors.company ? undefined : 'profile-control'} autoComplete="organization" maxLength={200} />
            <Input id="profile-role" name="role" label="Роль / Должность" labelView="outer" size={48} block
              className="profile-field-wide" fieldClassName={errors.role ? undefined : 'profile-control'}
              value={profile.role} error={errors.role} autoComplete="organization-title" maxLength={120}
              onChange={(event) => changeField('role', event.target.value)} />
            <Input id="profile-email" name="email" label="Рабочий e-mail" labelView="outer" size={48} block type="email"
              value={profile.email} onChange={(event) => changeField('email', event.target.value)}
              error={errors.email} fieldClassName={errors.email ? undefined : 'profile-control'} autoComplete="email" maxLength={254} />
            <Input id="profile-phone" name="phone" label="Номер телефона" labelView="outer" size={48} block type="tel"
              value={profile.phone} onChange={(event) => changeField('phone', event.target.value)}
              error={errors.phone} fieldClassName={errors.phone ? undefined : 'profile-control'} autoComplete="tel" maxLength={32} />
          </div>
        </form>
      </section>

      <section className="profile-panel" aria-labelledby="counterparties-title">
        <div className="profile-panel-heading">
          <div>
            <Typography.Title tag="h2" font="system" weight="semibold" className="profile-panel-title" id="counterparties-title">Контрагенты</Typography.Title>
            <Typography.Text tag="p" view="primary-small" className="profile-panel-description">Список связанных партнеров для автоматического расчета скоринга</Typography.Text>
          </div>
        </div>

        <form className="counterparty-add-form" onSubmit={addCounterparty} noValidate>
          <Input id="counterparty-query" name="counterparty" block size={48} placeholder="ИНН или наименование организации"
            aria-label="ИНН или наименование организации" value={query} maxLength={200} error={queryError || undefined}
            fieldClassName={queryError ? undefined : 'profile-control'}
            onChange={(event) => { setQuery(event.target.value); setQueryError(''); }} />
          <Button type="submit" view="secondary" size={40} leftAddons={<PlusSIcon aria-hidden="true" />} className="counterparty-add-button">Добавить</Button>
        </form>

        {counterparties.length ? (
          <ul className="counterparty-list" aria-label="Список контрагентов">
            {counterparties.map((entry, index) => {
              const Icon = kindIcons[entry.kind];
              return (
                <li className="counterparty-row" key={entry.id}>
                  <Circle size={40} backgroundColor="#F3F4F6" className="counterparty-icon"><Icon aria-hidden="true" /></Circle>
                  <div className="counterparty-info">
                    <Typography.Text tag="p" view="primary-small" weight="medium" className="counterparty-name">{entry.name}</Typography.Text>
                    <Typography.Text tag="p" view="secondary-medium" className="counterparty-meta">
                      {entry.inn ? `ИНН ${entry.inn}` : 'ИНН не указан'}<span aria-hidden="true"> · </span>{kindLabels[entry.kind]}
                    </Typography.Text>
                  </div>
                  <IconButton type="button" size={32} view="transparent" icon={CrossMIcon} className="counterparty-remove"
                    aria-label={`Удалить ${entry.name}${entry.inn ? `, ИНН ${entry.inn}` : ''}`}
                    onClick={() => removeCounterparty(entry, index)} />
                </li>
              );
            })}
          </ul>
        ) : <div className="counterparty-empty"><OfficeMIcon aria-hidden="true" /><Typography.Text tag="p" view="primary-small">Контрагентов пока нет. Добавьте организацию по ИНН или названию.</Typography.Text></div>}
      </section>

      <Typography.Text tag="p" view="secondary-small" className="profile-demo-note">Демо-профиль. Изменения сохраняются только в этом браузере.</Typography.Text>
      <Toast open={Boolean(notice)} title={notice} autoCloseDelay={6000} onClose={() => { setNotice(''); setRemoved(null); }}
        actionButton={removed ? <Button view="text" size={32} onClick={undoRemove}>Отменить</Button> : undefined} />
    </main>
  );
}
