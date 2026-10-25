import type { Counterparty, UserProfile } from '../types/profile';

export const demoProfile: UserProfile = {
  fullName: 'Константинопольский Константин К.',
  company: 'ООО «Город Нагатино»',
  role: 'Финансовый директор',
  email: 'k.konstantinopolsky@example.com',
  phone: '+7 (999) 000-24-11',
};

/** Вымышленные организации и ИНН, без проверки по реестру. */
export const demoCounterparties: Counterparty[] = [
  { id: 'supplier-demo', name: 'ООО «Ландыш и партнеры»', inn: '7700000001', kind: 'supplier' },
  { id: 'logistics-demo', name: 'АО «Северный логистический хаб»', inn: '7700000002', kind: 'logistics' },
  { id: 'buyer-demo', name: 'ООО «Циферблат Трейд»', inn: '7700000003', kind: 'buyer' },
];
