/**
 * Server-side data loaders for the homepage.
 * Each loader hits the corresponding Django backend endpoint and gracefully
 * falls back to representative seed data when the API is unreachable or empty,
 * so the homepage is never broken during development or backend migrations.
 *
 * Backend contracts mirror config/urls.py and the README:
 *   GET /api/v1/madadkar/campaigns/
 *   GET /api/v1/r4j/criminals/
 *   GET /api/v1/lms/courses/
 *   GET /api/v1/kindness-wall/listings/
 *   GET /api/v1/tabyin/contents/
 *   GET /api/v1/public-reports/subjects/
 */

import { safeApiFetch } from '@/lib/api';
import type { CampaignCard } from '@/components/home/WarFundSection';
import type { CriminalCard } from '@/components/home/JusticeSection';
import type { CourseCard } from '@/components/home/EducationSection';
import type { KindListing } from '@/components/home/KindnessSection';
import type { TabyinItem } from '@/components/home/TabyinSection';

type Paginated<T> = { results?: T[] } | T[];

function unwrap<T>(x: Paginated<T> | null): T[] {
  if (!x) return [];
  if (Array.isArray(x)) return x;
  return x.results ?? [];
}

// ─── Madadkar (warfund) ─────────────────────────────────────────────────────
type ApiCampaign = {
  slug: string; title: string;
  sponsor_name?: string;
  total_amount_rial?: number; share_price_rial?: number;
  shares_total?: number; shares_remaining?: number;
  progress_percent?: number; cover_image_url?: string;
};

export async function loadCampaigns(): Promise<CampaignCard[]> {
  const data = await safeApiFetch<Paginated<ApiCampaign>>(
    '/madadkar/campaigns/?page_size=4', { revalidate: 300, tags: ['campaigns'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.slice(0, 4).map((c) => ({
      slug: c.slug,
      title: c.title,
      sponsor: c.sponsor_name || 'گروه جهادی',
      totalAmount: c.total_amount_rial || 0,
      sharePrice: c.share_price_rial || 0,
      sharesTotal: c.shares_total || 0,
      sharesRemaining: c.shares_remaining || 0,
      progressPercent: c.progress_percent ?? 0,
      coverUrl: c.cover_image_url,
    }));
  }
  // fallback seed (mirrors design copy)
  const seed: CampaignCard = {
    slug: '', title: 'خرید پشه‌بند ضد دوربین‌های دید در شب برای جبهه‌ها',
    sponsor: 'گروه جهادی انصارالزهرا', totalAmount: 10_000_000_000, sharePrice: 0,
    sharesTotal: 1500, sharesRemaining: 496, progressPercent: 50,
  };
  return [
    { ...seed, slug: 'jabhe-1' },
    { ...seed, slug: 'jabhe-2' },
    { ...seed, slug: 'jabhe-3' },
    { ...seed, slug: 'jabhe-4' },
  ];
}

// ─── R4J ─────────────────────────────────────────────────────────────────────
type ApiCriminal = { slug: string; full_name: string; image_url?: string };
export async function loadCriminals(): Promise<CriminalCard[]> {
  const data = await safeApiFetch<Paginated<ApiCriminal>>(
    '/r4j/criminals/?page_size=3', { revalidate: 600, tags: ['criminals'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.slice(0, 3).map((p) => ({
      slug: p.slug, fullName: p.full_name, imageUrl: p.image_url,
    }));
  }
  return [
    { slug: 'salman-rushdie', fullName: 'سلمان رشدی' },
    { slug: 'reza-pahlavi',   fullName: 'رضا پهلوی' },
    { slug: 'yair-lapid',     fullName: 'یائیر لاپید' },
  ];
}

// ─── LMS ─────────────────────────────────────────────────────────────────────
type ApiCourse = { slug: string; title: string; instructor_name?: string; cover_image_url?: string; is_new?: boolean };
export async function loadCourses(): Promise<CourseCard[]> {
  const data = await safeApiFetch<Paginated<ApiCourse>>(
    '/lms/courses/?page_size=4&ordering=-created_at',
    { revalidate: 300, tags: ['courses'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.slice(0, 4).map((c) => ({
      slug: c.slug, title: c.title, instructor: c.instructor_name,
      coverUrl: c.cover_image_url, isNew: c.is_new ?? true,
    }));
  }
  return [
    { slug: 'documentary-1', title: 'دوره کارگردانی مستند', instructor: 'استاد دوره: وحید چیتی', isNew: true, toneFrom: '#1a1a1a', toneTo: '#444' },
    { slug: 'filmnameh-mostanad', title: 'فیلم‌نامه مستند', instructor: 'مدرس: سهیل کریمی', isNew: true, toneFrom: '#E55214', toneTo: '#FF8C2E' },
    { slug: 'filmnameh-cinema', title: 'فیلم‌نامه‌نویسی تیزر فرهنگی', instructor: 'سجاد سلیمان‌نژاد', isNew: true, toneFrom: '#1F1F1F', toneTo: '#333' },
    { slug: 'web-design', title: 'آموزش کامل طراحی سایت', instructor: 'اساتید: رسول خسروبیگی، مرتضی نوری مجد، علیرضا حسینی', isNew: true, toneFrom: '#6B21A8', toneTo: '#4338CA' },
  ];
}

// ─── Kindness ────────────────────────────────────────────────────────────────
type ApiListing = { slug: string; title: string; listing_type: 'need' | 'offer' };
export async function loadKindnessListings(): Promise<KindListing[]> {
  const data = await safeApiFetch<Paginated<ApiListing>>(
    '/kindness-wall/listings/?page_size=10', { revalidate: 180, tags: ['kindness'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.slice(0, 10).map((l) => ({
      slug: l.slug, title: l.title, type: l.listing_type,
    }));
  }
  return [
    { slug: 'k-1', title: 'نیازمند بیبیلک', type: 'need' },
    { slug: 'k-2', title: 'لورم ایپسوم متن سازمانی ساختاریافته با بیلیلک', type: 'need' },
    { slug: 'k-3', title: 'تو این اوضاع می‌تونم خریدای سالمندا رو انجام بدم', type: 'offer' },
    { slug: 'k-4', title: 'نیازمند بیبیلک خوبو', type: 'need' },
    { slug: 'k-5', title: 'به عنوان سرویس ایاب و ذهاب می‌تونم فعالیت کنم', type: 'offer' },
    { slug: 'k-6', title: 'نیازمند بیل', type: 'need' },
  ];
}

// ─── Tabyin ──────────────────────────────────────────────────────────────────
type ApiTabyin = { id: string; slug: string; title?: string; summary?: string; cover_image_url?: string };
export async function loadTabyinItems(): Promise<TabyinItem[]> {
  const data = await safeApiFetch<Paginated<ApiTabyin>>(
    '/tabyin/contents/?page_size=12', { revalidate: 180, tags: ['tabyin'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.slice(0, 12).map((t) => ({
      id: t.id, slug: t.slug, title: t.title, summary: t.summary,
      coverUrl: t.cover_image_url, variant: t.cover_image_url ? 'cover' : 'quote',
    }));
  }
  // designer-style masonry seed
  const tones: Array<[string, string]> = [
    ['#3FA797', '#0A6E64'], ['#0D8074', '#053832'], ['#3FA797', '#155F55'],
    ['#5DB3A4', '#0A6E64'], ['#0D8074', '#0A6E64'], ['#3FA797', '#053832'],
    ['#5DB3A4', '#0D8074'], ['#0A6E64', '#053832'], ['#3FA797', '#085C54'],
    ['#5DB3A4', '#085C54'], ['#0D8074', '#085C54'], ['#3FA797', '#0A6E64'],
  ];
  return tones.map((t, i) => ({
    id: `seed-${i}`, slug: `seed-${i}`,
    title: ['دهه‌ی فجر انقلاب اسلامی', 'منبر انقلاب اسلامی', '«جالدها میان ما»', 'حضرت معصومه (س)', 'مقاومت اسلامی', 'هنر مسلح مقاومت', 'کبوتر صلح', 'دفاع از وطن', 'ریشه در تاریخ', 'مقاومت', 'نسل سوم انقلاب', 'به یاد شهدا'][i],
    summary: i === 4 ? 'او به خاطر نقاشی‌های واقع‌گرایانه‌اش از رویدادهای مذهبی شهرت دارد. او خالق آثاری چون «عرش بر زمین افتاد»، «شیرین‌تر از عسل»، «آتش پرستاره شد» و «آخرین سرباز لشکر» است.' : undefined,
    variant: i === 4 ? 'quote' : undefined,
    tall: [0, 6].includes(i),
    toneFrom: t[0], toneTo: t[1],
  }));
}
