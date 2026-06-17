/**
 * Server-side data loaders for the homepage.
 * Each loader hits the corresponding Django backend endpoint and gracefully
 * falls back to representative seed data when the API is unreachable or empty,
 * so the homepage is never broken during development or backend migrations.
 *
 * Backend contracts mirror config/urls.py and the README:
 *   GET /api/v1/madadkar/campaigns/
 *   GET /api/v1/r4j/criminals/
 *   GET /api/v1/lms/categories/
 *   GET /api/v1/lms/courses/
 *   GET /api/v1/kindness-wall/categories/
 *   GET /api/v1/kindness-wall/listings/
 *   GET /api/v1/tabyin/contents/
 *   GET /api/v1/public-reports/subjects/
 */

import { safeApiFetch } from '@/lib/api';
import type { CampaignCard } from '@/components/home/WarFundSection';
import type { CriminalCard } from '@/components/home/JusticeSection';
import type { CourseCard, EduCategory } from '@/components/home/EducationSection';
import type { KindListing } from '@/components/home/KindnessSection';
import type { TabyinItem } from '@/components/home/TabyinSection';

type Paginated<T> = { results?: T[] } | T[];
function unwrap<T>(x: Paginated<T> | null): T[] {
  if (!x) return [];
  if (Array.isArray(x)) return x;
  return x.results ?? [];
}

/* ─── Madadkar (warfund) ─────────────────────────────────────────────── */
type ApiCampaign = {
  slug: string; title: string;
  sponsor_name?: string;
  total_amount_rial?: number;
  share_price_rial?: number;
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
  // 6 campaigns → fills 3 rows of 2 cols on desktop (clearly more than 2 rows of samples)
  const mk = (
    slug: string, title: string, sponsor: string,
    totalAmount: number, sharesTotal: number, sharesRemaining: number, progressPercent: number,
  ): CampaignCard => ({
    slug, title, sponsor, totalAmount, sharePrice: 0,
    sharesTotal, sharesRemaining, progressPercent,
  });
  return [
    mk('pashe-band-jabhe',    'تهیه پشه‌بند ضد دوربین‌های دید در شب برای مدافعان جبهه',  'گروه جهادی انصارالزهرا',   10_000_000_000, 1500, 496, 67),
    mk('darooye-emdadi',      'تأمین داروهای اضطراری بیمارستان صحرایی پشتیبان جبهه',     'مؤسسه شهید احمدی روشن',     6_500_000_000,   650, 220, 66),
    mk('logistic-mavanea',    'پشتیبانی لجستیکی گروه‌های جهادی مستقر در منطقه عملیاتی',  'گروه جهادی شهید کاظمی',     4_200_000_000,   420,  84, 80),
    mk('tajhizat-emdad',      'خرید تجهیزات امداد و نجات برای پایگاه پشتیبان مرزی',      'بسیج سازندگی استان',        8_900_000_000,   890, 312, 65),
    mk('shabake-aab',         'احداث شبکه آب‌رسانی به روستاهای جنگ‌زده غرب کشور',          'گروه جهادی شهید بهشتی',     5_400_000_000,   540, 168, 69),
    mk('paygah-edari',        'تجهیز پایگاه فرماندهی صحرایی و دفتر اداری منطقه عملیات',    'قرارگاه پشتیبانی مردمی',    7_700_000_000,   770, 405, 47),
  ];
}

/* ─── R4J ────────────────────────────────────────────────────────────── */
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
  // Seed: 7 criminals → fills 2 rows of 4 on desktop alongside the trophy CTA card
  return [
    { slug: 'salman-rushdie',  fullName: 'سلمان رشدی' },
    { slug: 'reza-pahlavi',    fullName: 'رضا پهلوی' },
    { slug: 'yair-lapid',      fullName: 'یائیر لاپید' },
    { slug: 'netanyahu',       fullName: 'بنیامین نتانیاهو' },
    { slug: 'trump',           fullName: 'دونالد ترامپ' },
    { slug: 'pompeo',          fullName: 'مایک پمپئو' },
    { slug: 'rajavi',          fullName: 'مسعود رجوی' },
  ];
}

/* ─── LMS ────────────────────────────────────────────────────────────── */
type ApiLmsCategory = { slug: string; title: string; courses_count?: number };
type ApiCourse = {
  slug: string; title: string; subtitle?: string;
  instructor_name?: string; level?: string;
  cover_image?: string;
  lessons_count?: number; estimated_duration_seconds?: number;
  enrollments_count?: number; graduates_count?: number;
  is_featured?: boolean; published_at?: string;
  category?: { slug?: string; title?: string };
};

export async function loadLmsCategories(): Promise<EduCategory[]> {
  const data = await safeApiFetch<Paginated<ApiLmsCategory>>(
    '/lms/categories/', { revalidate: 600, tags: ['lms-categories'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.map((c) => ({ slug: c.slug, title: c.title, count: c.courses_count }));
  }
  // Seed (fallback)
  return [
    { slug: 'rescue',     title: 'امداد و نجات' },
    { slug: 'security',   title: 'موارد امنیتی' },
    { slug: 'media',      title: 'سواد رسانه‌ای' },
    { slug: 'logistics',  title: 'لجستیک و پشتیبانی' },
    { slug: 'health',     title: 'بهداشت و درمان' },
    { slug: 'tabyin',     title: 'جهاد تبیین' },
    { slug: 'tech',       title: 'فناوری و طراحی' },
    { slug: 'leadership', title: 'مدیریت گروه‌های جهادی' },
  ];
}

export async function loadCourses(): Promise<CourseCard[]> {
  const data = await safeApiFetch<Paginated<ApiCourse>>(
    '/lms/courses/?page_size=12&ordering=-published_at',
    { revalidate: 300, tags: ['courses'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.map((c) => {
      const card: CourseCard = {
        slug: c.slug,
        title: c.title,
        subtitle: c.subtitle,
        instructor: c.instructor_name,
        level: c.level,
        coverUrl: c.cover_image,
        lessonsCount: c.lessons_count,
        durationSeconds: c.estimated_duration_seconds,
        enrollmentsCount: c.enrollments_count,
        isFeatured: c.is_featured,
        isNew: c.published_at
          ? Date.now() - new Date(c.published_at).getTime() < 1000 * 60 * 60 * 24 * 30
          : false,
        categorySlug: c.category?.slug,
      };
      return card;
    });
  }
  // Seed (fallback) — matches designer mockup
  const make = (
    slug: string, title: string, instructor: string,
    category: string, level: 'beginner' | 'intermediate' | 'advanced',
    lessons: number, hours: number,
    tone: [string, string], isNew = true,
  ): CourseCard => ({
    slug, title, instructor, level, lessonsCount: lessons,
    durationSeconds: hours * 3600, isNew, categorySlug: category,
    toneFrom: tone[0], toneTo: tone[1],
  });
  return [
    make('kargardani-mostanad',  'دوره کارگردانی مستند',           'استاد وحید چیتی',          'media',     'advanced',     24, 18, ['#1a1a1a', '#444']),
    make('filmnameh-mostanad',   'فیلم‌نامه‌نویسی مستند',           'مدرس سهیل کریمی',          'media',     'intermediate', 18, 12, ['#E55214', '#FF8C2E']),
    make('filmnameh-cinema',     'فیلم‌نامه‌نویسی تیزر فرهنگی',     'سجاد سلیمان‌نژاد',         'media',     'intermediate', 14,  9, ['#1F1F1F', '#333']),
    make('web-design',           'آموزش کامل طراحی سایت',           'رسول خسروبیگی، مرتضی نوری مجد', 'tech', 'advanced',    32, 24, ['#6B21A8', '#4338CA']),
    make('amdad-1',              'امداد و نجات مقدماتی',             'دکتر علی محمدی',           'rescue',    'beginner',     12,  6, ['#0D8074', '#053832']),
    make('media-lit',            'سواد رسانه‌ای و جنگ ادراکی',      'دکتر رضایی',              'tabyin',    'beginner',      9,  6, ['#155F55', '#0D8074']),
    make('jihadi-mgmt',          'مدیریت گروه‌های جهادی',           'مهندس سلطانی',             'leadership','intermediate', 16, 10, ['#0A6E64', '#085C54']),
    make('photo-khabari',        'عکاسی خبری و میدانی',              'استاد عظیمی',              'media',     'intermediate', 10,  7, ['#92580E', '#5F3A09']),
  ];
}

/* ─── Kindness Wall ──────────────────────────────────────────────────── */
type ApiKindnessCategory = { slug: string; title: string };
type ApiListing = {
  id?: string; slug: string;
  listing_type: 'need' | 'offer';
  title: string;
  category?: { title?: string };
  province?: string; city?: string; district?: string;
  owner_full_name_snapshot?: string;
  owner_avatar_snapshot?: string;
  cover_image?: string;
  published_at?: string;
  expires_at?: string;
  view_count?: number;
};

export async function loadKindnessListings(): Promise<KindListing[]> {
  const data = await safeApiFetch<Paginated<ApiListing>>(
    '/kindness-wall/listings/?page_size=12&ordering=-published_at',
    { revalidate: 180, tags: ['kindness'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.map((l) => ({
      slug: l.slug,
      title: l.title,
      type: l.listing_type,
      categoryTitle: l.category?.title,
      province: l.province,
      city: l.city,
      district: l.district,
      ownerName: l.owner_full_name_snapshot,
      ownerAvatar: l.owner_avatar_snapshot,
      coverImage: l.cover_image,
      publishedAt: l.published_at,
      expiresAt: l.expires_at,
      viewCount: l.view_count,
    }));
  }
  // Seed (fallback) — 12 listings: 6 need + 6 offer (each filter shows 2 full rows of 3)
  const now = Date.now();
  return [
    { slug: 'k-1',  title: 'نیازمند یخچال نو یا دست‌دوم سالم برای خانواده محترم پنج‌نفره',         type: 'need',  categoryTitle: 'لوازم خانگی',   city: 'تهران',   province: 'تهران',          ownerName: 'فاطمه ع.',       publishedAt: new Date(now - 1000 * 60 * 30).toISOString(),         viewCount: 248 },
    { slug: 'k-2',  title: 'آماده اهدای کتاب‌های درسی مقاطع راهنمایی و دبیرستان',                  type: 'offer', categoryTitle: 'لوازم آموزشی', city: 'مشهد',   province: 'خراسان رضوی',    ownerName: 'حسن م.',         publishedAt: new Date(now - 1000 * 60 * 60 * 2).toISOString(),     viewCount: 184 },
    { slug: 'k-3',  title: 'درخواست کمک هزینه درمان بیماری خاص فرزند خانواده کم‌بضاعت',           type: 'need',  categoryTitle: 'سلامت و درمان', city: 'اصفهان', province: 'اصفهان',         ownerName: 'محمد ر.',        publishedAt: new Date(now - 1000 * 60 * 60 * 6).toISOString(),     viewCount: 1245 },
    { slug: 'k-4',  title: 'اهدای پوشاک نو زمستانی برای کودکان ۳ تا ۸ سال مناطق محروم',             type: 'offer', categoryTitle: 'پوشاک',         city: 'شیراز',  province: 'فارس',           ownerName: 'گروه خادمان',    publishedAt: new Date(now - 1000 * 60 * 60 * 12).toISOString(),    viewCount: 92 },
    { slug: 'k-5',  title: 'استخدام کمک‌فروشنده پاره‌وقت برای مغازه لوازم خانگی',                 type: 'need',  categoryTitle: 'فرصت شغلی',     city: 'تبریز',  province: 'آذربایجان شرقی', ownerName: 'بازرگانی شهاب',  publishedAt: new Date(now - 1000 * 60 * 60 * 24).toISOString(),    viewCount: 312 },
    { slug: 'k-6',  title: 'ارائه مشاوره حقوقی رایگان برای خانواده‌های نیازمند',                  type: 'offer', categoryTitle: 'خدمات تخصصی',  city: 'قم',     province: 'قم',             ownerName: 'وکیل سلیمی',     publishedAt: new Date(now - 1000 * 60 * 60 * 36).toISOString(),    viewCount: 567 },
    { slug: 'k-7',  title: 'نیاز فوری به ویلچر و تجهیزات پزشکی برای جانباز عزیز',                 type: 'need',  categoryTitle: 'سلامت و درمان', city: 'کرج',    province: 'البرز',          ownerName: 'حمید س.',        publishedAt: new Date(now - 1000 * 60 * 60 * 48).toISOString(),    viewCount: 421 },
    { slug: 'k-8',  title: 'اهدای میز و صندلی اداری نو برای دفاتر مؤسسات خیریه',                  type: 'offer', categoryTitle: 'تجهیزات اداری', city: 'تهران',  province: 'تهران',          ownerName: 'شرکت پارس‌تجهیز', publishedAt: new Date(now - 1000 * 60 * 60 * 60).toISOString(),    viewCount: 137 },
    { slug: 'k-9',  title: 'نیازمند بسته‌های ارزاق ماه مبارک رمضان برای ۲۰ خانواده محروم',         type: 'need',  categoryTitle: 'مواد غذایی',    city: 'اهواز',  province: 'خوزستان',        ownerName: 'هیئت ابوالفضل',  publishedAt: new Date(now - 1000 * 60 * 60 * 72).toISOString(),    viewCount: 856 },
    { slug: 'k-10', title: 'ارائه کلاس آموزش رایگان زبان انگلیسی برای دانش‌آموزان مقطع متوسطه',     type: 'offer', categoryTitle: 'آموزش',         city: 'رشت',    province: 'گیلان',          ownerName: 'استاد رحیمی',    publishedAt: new Date(now - 1000 * 60 * 60 * 84).toISOString(),    viewCount: 298 },
    { slug: 'k-11', title: 'نیاز به کمک هزینه جهیزیه برای خانواده زوج جوان جانباز',               type: 'need',  categoryTitle: 'لوازم خانگی',   city: 'یزد',    province: 'یزد',            ownerName: 'مادر شهید رضایی', publishedAt: new Date(now - 1000 * 60 * 60 * 96).toISOString(),    viewCount: 712 },
    { slug: 'k-12', title: 'پیشنهاد رایگان خدمات تعمیرات لوازم خانگی برای خانواده‌های کم‌بضاعت',    type: 'offer', categoryTitle: 'خدمات فنی',     city: 'کرمان',  province: 'کرمان',          ownerName: 'تعمیرگاه برادران', publishedAt: new Date(now - 1000 * 60 * 60 * 108).toISOString(),   viewCount: 184 },
  ];
}

/* ─── Tabyin ─────────────────────────────────────────────────────────── */
type ApiTabyin = {
  id: string; slug: string; title?: string; summary?: string;
  cover_image_url?: string;
};

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
  // Exactly 8 tiles → 2 rows of 4 on desktop, perfect designer rhythm
  const tones: Array<[string, string]> = [
    ['#3FA797', '#0A6E64'], ['#0D8074', '#053832'], ['#3FA797', '#155F55'],
    ['#5DB3A4', '#0A6E64'], ['#0D8074', '#0A6E64'], ['#3FA797', '#053832'],
    ['#5DB3A4', '#0D8074'], ['#0A6E64', '#053832'],
  ];
  const titles = [
    'دهه‌ی فجر انقلاب اسلامی', 'منبر انقلاب اسلامی', '«جلادها میان ما»',
    'حضرت معصومه (س)', 'مقاومت اسلامی', 'هنر مسلح مقاومت',
    'کبوتر صلح', 'دفاع از وطن',
  ];
  return tones.map((t, i) => ({
    id: `seed-${i}`, slug: `seed-${i}`,
    title: titles[i],
    summary: i === 4
      ? 'او به خاطر نقاشی‌های واقع‌گرایانه‌اش از رویدادهای مذهبی شهرت دارد. خالق آثاری چون «عرش بر زمین افتاد»، «شیرین‌تر از عسل» و «آخرین سرباز لشکر» است.'
      : undefined,
    variant: i === 4 ? 'quote' : undefined,
    tall: false,
    toneFrom: t[0], toneTo: t[1],
  }));
}
