import { useState, type FormEvent } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Checkbox } from '@alfalab/core-components/checkbox';
import { Circle } from '@alfalab/core-components/icon-view/circle';
import { Input } from '@alfalab/core-components/input';
import { Modal } from '@alfalab/core-components/modal';
import { PasswordInput } from '@alfalab/core-components/password-input';
import { PhoneInput } from '@alfalab/core-components/phone-input';
import { Select } from '@alfalab/core-components/select';
import { Tabs, Tab } from '@alfalab/core-components/tabs';
import { Typography } from '@alfalab/core-components/typography';
import { ArrowRightMIcon } from '@alfalab/icons-glyph/ArrowRightMIcon';
import { CheckmarkMIcon } from '@alfalab/icons-glyph/CheckmarkMIcon';
import { HeadsetMIcon } from '@alfalab/icons-glyph/HeadsetMIcon';
import { MailMIcon } from '@alfalab/icons-glyph/MailMIcon';
import { ShieldMIcon } from '@alfalab/icons-glyph/ShieldMIcon';
import { UserMIcon } from '@alfalab/icons-glyph/UserMIcon';
import { DEMO_EMAIL, DEMO_PASSWORD, passwordChecks, registrationProfile, validateDemoLogin,
  validateRegistration, type RegistrationErrors, type RegistrationFields } from '../lib/auth';
import { businessIndustries, staffSizes, type UserProfile } from '../types/profile';
import './entry.css';

const industryOptions = businessIndustries.map((value) => ({ key: value, content: value }));
const staffOptions = staffSizes.map((value) => ({ key: value, content: value }));
const initialRegistration: RegistrationFields = {
  fullName: '', company: '', role: '', industry: '', staffSize: '', email: '', phone: '', password: '', consent: false,
};
const benefits = ['Контекст компании и вашей должности в одном профиле', 'Новости и контрагенты, важные для вашего бизнеса', 'Единое пространство для будущих аналитических отчётов'];

export function EntryPage({ mode, onModeChange, onEnter }: {
  mode: 'login' | 'register';
  onModeChange: (mode: 'login' | 'register') => void;
  onEnter: (options: { remember: boolean; profile?: UserProfile }) => void;
}) {
  const registering = mode === 'register';
  const [registration, setRegistration] = useState(initialRegistration);
  const [errors, setErrors] = useState<RegistrationErrors>({});
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [remember, setRemember] = useState(false);
  const [formError, setFormError] = useState('');
  const [info, setInfo] = useState<'bank' | 'support' | 'demo' | 'password' | null>(null);
  const checks = passwordChecks(registration.password);

  function change<K extends keyof RegistrationFields>(field: K, value: RegistrationFields[K]) {
    setRegistration((previous) => ({ ...previous, [field]: value }));
    setErrors((previous) => ({ ...previous, [field]: undefined }));
    setFormError('');
  }

  function switchMode(next: 'login' | 'register') {
    setErrors({}); setFormError(''); onModeChange(next);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError('');
    if (registering) {
      const nextErrors = validateRegistration(registration);
      setErrors(nextErrors);
      const firstInvalid = Object.keys(nextErrors)[0];
      if (firstInvalid) {
        const field = event.currentTarget.elements.namedItem(firstInvalid);
        if (field instanceof HTMLElement) field.focus();
        return;
      }
    } else {
      const error = validateDemoLogin(email, password);
      if (error) { setFormError(error); return; }
    }
    try {
      onEnter({ remember: registering ? false : remember, ...(registering ? { profile: registrationProfile(registration) } : {}) });
    } catch {
      setFormError('Не удалось сохранить демо-профиль или сессию. Разрешите локальное хранилище в браузере и попробуйте снова.');
    }
  }

  return (
    <div className="entry-page">
      <header className="entry-header">
        <a className="brand" href="#/login" aria-label="Альфа-Бизнес — вход"><span className="brand__mark" aria-hidden="true">А</span><span>Альфа-Бизнес<span className="brand__divider" /><span className="brand__service">Интеллект & Мониторинг</span></span></a>
        <span className="entry-header-status">Демонстрационный кабинет</span>
        <Button view="text" size={40} className="entry-support" onClick={() => setInfo('support')}><span><HeadsetMIcon aria-hidden="true" />Поддержка</span></Button>
      </header>

      <main className="entry-main">
        <div className="entry-card">
          <section className="entry-story" aria-labelledby="entry-story-title">
            <div className="entry-story-brand"><span className="entry-brand-tile" aria-hidden="true">А</span><div>Альфа-Бизнес<span>ИНТЕЛЛЕКТ & МОНИТОРИНГ</span></div></div>
            <span className="entry-story-tag">Единый профиль компании</span>
            <Typography.Title tag="h2" font="system" className="entry-story-title" id="entry-story-title">Интеллектуальная аналитика и риск-мониторинг для вашего бизнеса</Typography.Title>
            <Typography.Text tag="p" className="entry-story-lead">Новости, контрагенты и аналитика — в едином пространстве для принятия решений.</Typography.Text>
            <ul className="entry-benefits">{benefits.map((benefit) => <li key={benefit}><CheckmarkMIcon aria-hidden="true" /><span>{benefit}</span></li>)}</ul>
            <div className="entry-story-note"><ShieldMIcon aria-hidden="true" /><p>Сейчас это прототип. Банковская авторизация, проверка контрагентов и персональный AI-анализ пока не подключены.</p></div>
          </section>

          <section className="entry-form-panel" aria-labelledby="entry-title">
            <div className="entry-form-topline"><span>ДЕМО-ДОСТУП</span><span className="entry-language" aria-label="Язык интерфейса: русский">RU</span></div>
            <div className="entry-form-heading">
              <Circle size={56} backgroundColor="#F3F4F6"><UserMIcon aria-hidden="true" /></Circle>
              <Typography.Title tag="h1" font="system" weight="semibold" className="entry-title" id="entry-title">{registering ? 'Регистрация в кабинете' : 'Вход в кабинет'}</Typography.Title>
              <Typography.Text tag="p" className="entry-subtitle">{registering ? 'Расскажите о себе и вашей компании' : 'Все важные события для бизнеса — в одном месте'}</Typography.Text>
            </div>

            <Tabs selectedId={mode} onChange={(_, { selectedId }) => switchMode(selectedId === 'register' ? 'register' : 'login')}
              view="secondary" tagView="filled" tagShape="rounded" size="s" className="entry-tabs">
              <Tab id="login" title="Вход" /><Tab id="register" title="Регистрация" />
            </Tabs>

            <Button view="accent" size={48} block className="entry-bank-button" onClick={() => setInfo('bank')}>
              <span className="entry-bank-button-content"><span className="entry-bank-letter" aria-hidden="true">А</span>{registering ? 'Регистрация через Альфа-Бизнес' : 'Войти через Альфа-ID Бизнес'}</span>
            </Button>
            <div className="entry-divider"><span>{registering ? 'ИЛИ ЗАПОЛНИТЕ ДАННЫЕ ВРУЧНУЮ' : 'ИЛИ ЧЕРЕЗ УЧЁТНУЮ ЗАПИСЬ'}</span></div>

            <form onSubmit={submit} noValidate className="entry-form">
              {registering ? (
                <div className="entry-fields">
                  <Input name="fullName" label="ФИО сотрудника *" labelView="outer" size={48} block maxLength={160} autoComplete="name"
                    className="entry-field-wide" fieldClassName={errors.fullName ? undefined : 'entry-control'} placeholder="Иванов Иван Иванович"
                    value={registration.fullName} error={errors.fullName} onChange={(event) => change('fullName', event.target.value)} />
                  <Input name="company" label="Компания / ИНН *" labelView="outer" size={48} block maxLength={200} autoComplete="organization"
                    fieldClassName={errors.company ? undefined : 'entry-control'} placeholder="Название или 10 цифр ИНН"
                    value={registration.company} error={errors.company} onChange={(event) => change('company', event.target.value)} />
                  <Select name="industry" label="Отрасль бизнеса" labelView="outer" size={48} block options={industryOptions} placeholder="Выберите отрасль"
                    fieldProps={{ fieldClassName: errors.industry ? undefined : 'entry-control' }} selected={registration.industry || null}
                    error={errors.industry} onChange={({ selected }) => change('industry', selected?.key || '')} />
                  <Input name="role" label="Должность в компании *" labelView="outer" size={48} block maxLength={120} autoComplete="organization-title"
                    fieldClassName={errors.role ? undefined : 'entry-control'} placeholder="Например, главный казначей"
                    value={registration.role} error={errors.role} onChange={(event) => change('role', event.target.value)} />
                  <Select name="staffSize" label="Размер штата" labelView="outer" size={48} block options={staffOptions} placeholder="Выберите размер"
                    fieldProps={{ fieldClassName: errors.staffSize ? undefined : 'entry-control' }} selected={registration.staffSize || null}
                    error={errors.staffSize} onChange={({ selected }) => change('staffSize', selected?.key || '')} />
                  <Input name="email" label="Рабочий e-mail *" labelView="outer" size={48} block type="email" maxLength={254} autoComplete="email"
                    fieldClassName={errors.email ? undefined : 'entry-control'} placeholder="name@company.ru"
                    value={registration.email} error={errors.email} onChange={(event) => change('email', event.target.value)} />
                  <PhoneInput name="phone" label="Рабочий телефон" labelView="outer" size={48} block autoComplete="tel"
                    fieldClassName={errors.phone ? undefined : 'entry-control'} placeholder="+7 999 000 00 00"
                    value={registration.phone} error={errors.phone} onChange={(event) => change('phone', event.target.value)} />
                  <PasswordInput name="password" label="Пароль для демо-входа *" labelView="outer" size={48} block maxLength={128} autoComplete="off"
                    className="entry-field-wide" fieldClassName={errors.password ? undefined : 'entry-control'} value={registration.password}
                    error={errors.password} onChange={(event) => change('password', event.target.value)}
                    passwordHint={{ hidden: 'Показать пароль', visible: 'Скрыть пароль' }}
                    hint={registration.password ? `Выполнено ${checks.filter(Boolean).length} из 3 требований: 8–128 символов, буква, цифра` : '8–128 символов, минимум одна буква и одна цифра. Не используйте настоящий пароль.'} />
                  <Checkbox name="consent" size={20} align="start" block className="entry-field-wide" checked={registration.consent}
                    label="Понимаю, что создаю локальный демонстрационный профиль, а не банковскую учётную запись"
                    error={errors.consent} onChange={(_, { checked }) => change('consent', checked)} />
                </div>
              ) : (
                <div className="entry-login-fields">
                  <Input name="email" label="Рабочий e-mail" labelView="outer" size={48} block type="email" maxLength={254} autoComplete="off"
                    fieldClassName="entry-control" leftAddons={<MailMIcon aria-hidden="true" />} value={email} onChange={(event) => { setEmail(event.target.value); setFormError(''); }} />
                  <PasswordInput name="password" label="Пароль доступа" labelView="outer" size={48} block maxLength={128} autoComplete="off"
                    fieldClassName="entry-control" value={password} onChange={(event) => { setPassword(event.target.value); setFormError(''); }}
                    passwordHint={{ hidden: 'Показать пароль', visible: 'Скрыть пароль' }} />
                  <div className="entry-login-options"><Checkbox size={20} compact checked={remember} label="Запомнить демо-доступ на 30 дней"
                    onChange={(_, { checked }) => setRemember(checked)} /><Button view="text" size={32} onClick={() => setInfo('password')}>Забыли пароль?</Button></div>
                </div>
              )}

              {formError && <p role="alert" className="entry-form-error">{formError}</p>}
              <Button type="submit" view="primary" size={48} block className="entry-submit" rightAddons={<ArrowRightMIcon aria-hidden="true" />}>
                {registering ? 'Создать демо-профиль' : 'Войти в демо-кабинет'}
              </Button>
              {registering ? <div className="entry-switch">Уже зарегистрированы? <Button view="text" size={32} onClick={() => switchMode('login')}>Войти</Button></div> : (
                <p className="entry-demo-credentials">Демо-доступ уже заполнен:<br /><span>{DEMO_EMAIL}</span> · <span>{DEMO_PASSWORD}</span></p>
              )}
            </form>
            <p className="entry-demo-notice">{registering ? 'Данные сохранятся только в этом браузере. Пароль не сохраняется и не создаёт учётную запись; для повторного входа используйте демо-доступ.' : 'Это демонстрация, не банковская авторизация. Не вводите реальные пароли.'}</p>
          </section>
        </div>
      </main>

      <footer className="entry-footer"><span>Альфа-Бизнес · Прототип интерфейса</span><div>{['Конфиденциальность', 'Безопасность данных', 'Условия демо'].map((label) => <Button key={label} size={32} view="text" onClick={() => setInfo('demo')}>{label}</Button>)}</div></footer>

      <Modal open={info !== null} onClose={() => setInfo(null)} hasCloser size={500}>
        <Modal.Header title={info === 'bank' ? 'Альфа-Бизнес пока не подключён' : info === 'support' ? 'Поддержка' : info === 'password' ? 'Восстановление пароля' : 'О демонстрационном режиме'} />
        <Modal.Content><p className="entry-modal-text">{info === 'bank' ? 'Эта кнопка — заглушка. Перехода в банк, импорта данных и авторизации не происходит. Для просмотра приложения используйте демо-вход или создайте локальный демо-профиль.' : info === 'support' ? 'Канал поддержки пока не подключён. Это демонстрационный интерфейс, не действующий банковский сервис.' : info === 'password' ? `Восстановление реального пароля пока недоступно. Для демо-входа используйте ${DEMO_EMAIL} и ${DEMO_PASSWORD}.` : 'Профиль хранится локально в браузере. Пароли не сохраняются и не отправляются на сервер. Флаг демо-доступа не является защитой данных. Альфа-ID, 2FA и банковская проверка не подключены. Не вводите реальные персональные или банковские данные.'}</p></Modal.Content>
        <Modal.Footer><Button view="secondary" size={40} onClick={() => setInfo(null)}>Понятно</Button></Modal.Footer>
      </Modal>
    </div>
  );
}
