/**
 * Site-wide navigation: primary nav, footer nav, megamenu groups.
 * Designed to mirror the backend apps under /api/v1/* (kept in sync with config/urls.py).
 */

export type NavItem = {
  label: string;
  href: string;
  description?: string;
  badge?: string;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export const primaryNav: NavItem[] = [
  { label: 'صفحه اصلی', href: '/' },
  { label: 'جهاد تبیین', href: '/tabyin' },
  { label: 'دیوار مهربانی', href: '/kindness-wall' },
  { label: 'مددکاری', href: '/madadkar' },
  { label: 'آموزش', href: '/lms' },
  { label: 'جایزه عدالت', href: '/r4j' },
  { label: 'گزارش مردمی', href: '/public-reports' },
  { label: 'درباره ما', href: '/about' },
  { label: 'تماس با ما', href: '/contact' },
];

export const footerNav: NavGroup[] = [
  {
    label: 'فعالیت‌ها',
    items: [
      { label: 'جهاد تبیین', href: '/tabyin' },
      { label: 'دیوار مهربانی', href: '/kindness-wall' },
      { label: 'مددکاری', href: '/madadkar' },
      { label: 'مدرسه آموزشی', href: '/lms' },
      { label: 'جایزه عدالت', href: '/r4j' },
    ],
  },
  {
    label: 'حساب کاربری',
    items: [
      { label: 'ورود / ثبت‌نام', href: '/auth/login' },
      { label: 'داشبورد من', href: '/dashboard' },
      { label: 'پشتیبانی', href: '/support' },
      { label: 'اعلان‌ها', href: '/notifications' },
    ],
  },
  {
    label: 'سازمان',
    items: [
      { label: 'درباره ما', href: '/about' },
      { label: 'حریم خصوصی', href: '/privacy' },
      { label: 'قوانین و مقررات', href: '/terms' },
      { label: 'سؤالات متداول', href: '/faq' },
      { label: 'تماس با ما', href: '/contact' },
    ],
  },
];
