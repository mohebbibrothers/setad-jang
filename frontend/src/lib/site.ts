/**
 * Central site configuration — used by SEO, metadata, sitemap, JSON-LD, etc.
 * Single source of truth for branding strings.
 */

export const siteConfig = {
  name: 'بعثت مردم',
  shortName: 'بعثت مردم',
  nameEn: 'Besat-e Mardom',
  slogan: 'سامانه‌ای برای جهاد تبیین، مددکاری، آموزش و همبستگی مردم ایران',
  description:
    'بعثت مردم؛ پلتفرم یکپارچه مردمی برای جهاد تبیین، گزارش‌های مردمی، دیوار مهربانی، آموزش، مددکاری و حمایت از مظلومان جهان.',
  keywords: [
    'بعثت مردم',
    'ستاد جنگ',
    'جهاد تبیین',
    'مددکاری',
    'دیوار مهربانی',
    'گزارش مردمی',
    'آموزش جهادی',
    'حمایت از مظلومان',
    'فیلسطین',
    'ایران',
    'reward for justice',
  ],
  url: process.env.NEXT_PUBLIC_SITE_URL || 'https://setadjang.ir',
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  locale: 'fa_IR',
  direction: 'rtl' as const,
  themeColor: '#1F8A7A',
  ogImage: '/og/cover.png',

  contact: {
    email: 'info@setadjang.ir',
    phone: '',
  },

  social: {
    eitaa: 'https://eitaa.com/setadjang',
    telegram: '',
    instagram: '',
    youtube: '',
    aparat: '',
    twitter: '',
  },

  organization: {
    legalName: 'بعثت مردم',
    legalNameEn: 'Besat-e Mardom',
    foundingDate: '2025',
    addressCountry: 'IR',
  },
} as const;

export type SiteConfig = typeof siteConfig;
