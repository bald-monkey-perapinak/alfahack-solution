export const businessIndustries = ['Оптовая торговля', 'Логистика и ВЭД', 'Производство', 'IT и Телеком', 'Строительство'] as const;
export const staffSizes = ['до 50 сотрудников', '50–250 сотрудников', 'более 250 сотрудников'] as const;

export interface UserProfile {
  fullName: string;
  company: string;
  role: string;
  email: string;
  phone: string;
  industry?: (typeof businessIndustries)[number];
  staffSize?: (typeof staffSizes)[number];
  companyInn?: string;
}

export type ProfileErrors = Partial<Record<keyof UserProfile, string>>;

export interface Counterparty {
  id: string;
  name: string;
  inn?: string;
  kind: 'supplier' | 'logistics' | 'buyer' | 'other';
}
