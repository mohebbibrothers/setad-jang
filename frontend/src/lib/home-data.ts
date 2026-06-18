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
/**
 * Mirrors apps.madadkar.serializers.CampaignPublicListSerializer exactly.
 * Monetary fields are stored in TOMAN; the UI multiplies by 10 to render
 * Rial (as required by the designer's mockup).
 */
type ApiSponsor = { id?: number; name: string; slug?: string; logo?: string | null };
type ApiCampaign = {
  id?: number;
  slug: string;
  title: string;
  sponsor?: ApiSponsor;
  cover_image?: string | null;
  total_amount?: number;          // Toman
  share_price?: number;           // Toman
  total_shares?: number;
  purchased_shares?: number;
  remaining_shares?: number;
  progress_percent?: number;
  is_fully_funded?: boolean;
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
      sponsor: c.sponsor?.name || 'گروه جهادی',
      totalAmount: c.total_amount ?? 0,
      sharePrice: c.share_price ?? 0,
      sharesTotal: c.total_shares ?? 0,
      sharesRemaining: c.remaining_shares ?? 0,
      progressPercent: c.progress_percent ?? 0,
      coverUrl: c.cover_image ?? undefined,
    }));
  }
  // 4 campaigns → exactly 2 rows × 2 cols on desktop (matches designer mockup).
  // Each gets a distinct tone so the gradient fallback covers feel curated.
  const mk = (
    slug: string, title: string, sponsor: string,
    totalAmount: number, sharesTotal: number, sharesRemaining: number, progressPercent: number,
    toneFrom: string, toneTo: string,
  ): CampaignCard => ({
    slug, title, sponsor, totalAmount, sharePrice: Math.floor(totalAmount / sharesTotal),
    sharesTotal, sharesRemaining, progressPercent, toneFrom, toneTo,
  });
  return [
    mk('pashe-band-jabhe',    'تهیه پشه‌بند ضد دوربین‌های دید در شب برای مدافعان جبهه',  'گروه جهادی انصارالزهرا',   1_000_000_000, 1500, 750, 50, '#0D8074', '#053832'),
    mk('darooye-emdadi',      'تأمین داروهای اضطراری بیمارستان صحرایی پشتیبان جبهه',     'مؤسسه شهید احمدی روشن',     1_000_000_000,  650, 215, 67, '#155F55', '#0A6E64'),
    mk('logistic-mavanea',    'پشتیبانی لجستیکی گروه‌های جهادی مستقر در منطقه عملیاتی',  'گروه جهادی شهید کاظمی',     1_000_000_000,  420,  84, 80, '#2FA08D', '#0A6E64'),
    mk('tajhizat-emdad',      'خرید تجهیزات امداد و نجات برای پایگاه پشتیبان مرزی',      'بسیج سازندگی استان',        1_000_000_000,  890, 484, 46, '#3FA797', '#155F55'),
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
  // Seed: 8 criminals → exactly 2 pages of 4 in the new pager-driven row
  return [
    { slug: 'salman-rushdie',  fullName: 'سلمان رشدی' },
    { slug: 'reza-pahlavi',    fullName: 'رضا پهلوی' },
    { slug: 'yair-lapid',      fullName: 'یائیر لاپید' },
    { slug: 'netanyahu',       fullName: 'بنیامین نتانیاهو' },
    { slug: 'trump',           fullName: 'دونالد ترامپ' },
    { slug: 'pompeo',          fullName: 'مایک پمپئو' },
    { slug: 'rajavi',          fullName: 'مسعود رجوی' },
    { slug: 'gallant',         fullName: 'یوآو گالانت' },
  ];
}

/* ─── LMS ────────────────────────────────────────────────────────────── */
type ApiLmsCategory = { slug: string; title: string; courses_count?: number };
/**
 * Mirrors apps.lms.serializers.CourseSummarySerializer.Meta.fields exactly.
 * (See apps/lms/serializers.py — CourseSummarySerializer).
 */
type ApiCourse = {
  id?: number;
  slug: string;
  title: string;
  subtitle?: string;
  short_description?: string;
  instructor_name?: string;
  instructor_avatar?: string | null;
  level?: 'beginner' | 'intermediate' | 'advanced' | 'professional' | string;
  status?: string;
  is_featured?: boolean;
  cover_image?: string | null;
  lessons_count?: number;
  estimated_duration_seconds?: number;
  enrollments_count?: number;
  graduates_count?: number;
  published_at?: string;
  category?: { id?: number; slug?: string; title?: string };
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
        instructorAvatarUrl: c.instructor_avatar ?? undefined,
        level: c.level,
        coverUrl: c.cover_image ?? undefined,
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
  // Seed (fallback) — 8 courses across 4 categories.
  // Note: `isNew` and `isFeatured` are NOT hard-coded here — the
  // EducationSection derives them at render time from real signals
  // (published_at < 30 days → isNew; enrollments > average → isFeatured),
  // exactly the same logic that will fire against live backend data.
  const now = Date.now();
  const daysAgo = (d: number) => new Date(now - d * 24 * 3600 * 1000).toISOString();
  const make = (
    slug: string, title: string, instructor: string,
    category: string, level: 'beginner' | 'intermediate' | 'advanced' | 'professional',
    lessons: number, hours: number,
    tone: [string, string],
    extra: Partial<CourseCard> & { publishedDaysAgo?: number } = {},
  ): CourseCard => {
    const days = extra.publishedDaysAgo ?? 60;
    return {
      slug, title, instructor, level, lessonsCount: lessons,
      durationSeconds: hours * 3600, categorySlug: category,
      toneFrom: tone[0], toneTo: tone[1],
      enrollmentsCount: extra.enrollmentsCount ?? 200,
      // isNew is computed in the section from publishedDaysAgo; we still set
      // it here so the seed previews behave correctly when no API is around.
      isNew: days <= 30,
    };
  };
  return [
    make('kargardani-mostanad', 'دوره کارگردانی مستند',          'استاد وحید چیتی',          'media',     'advanced',     24, 18, ['#1a1a1a', '#444'],    { enrollmentsCount: 1240, publishedDaysAgo: 12 }),
    make('filmnameh-mostanad',  'فیلم‌نامه‌نویسی مستند',          'مدرس سهیل کریمی',          'media',     'intermediate', 18, 12, ['#E55214', '#FF8C2E'], { enrollmentsCount: 860,  publishedDaysAgo: 22 }),
    make('filmnameh-cinema',    'فیلم‌نامه‌نویسی تیزر فرهنگی',    'سجاد سلیمان‌نژاد',         'media',     'intermediate', 14,  9, ['#1F1F1F', '#333'],    { enrollmentsCount: 420,  publishedDaysAgo: 55 }),
    make('web-design',          'آموزش کامل طراحی سایت',          'رسول خسروبیگی، مرتضی نوری مجد', 'tech', 'professional', 32, 24, ['#6B21A8', '#4338CA'], { enrollmentsCount: 2150, publishedDaysAgo: 8 }),
    make('amdad-1',             'امداد و نجات مقدماتی',            'دکتر علی محمدی',           'rescue',    'beginner',     12,  6, ['#0D8074', '#053832'], { enrollmentsCount: 980,  publishedDaysAgo: 40 }),
    make('media-lit',           'سواد رسانه‌ای و جنگ ادراکی',     'دکتر رضایی',              'tabyin',    'beginner',      9,  6, ['#155F55', '#0D8074'], { enrollmentsCount: 1340, publishedDaysAgo: 18 }),
    make('jihadi-mgmt',         'مدیریت گروه‌های جهادی',          'مهندس سلطانی',             'leadership','intermediate', 16, 10, ['#0A6E64', '#085C54'], { enrollmentsCount: 560,  publishedDaysAgo: 90 }),
    make('photo-khabari',       'عکاسی خبری و میدانی',             'استاد عظیمی',              'media',     'intermediate', 10,  7, ['#92580E', '#5F3A09'], { enrollmentsCount: 720,  publishedDaysAgo: 70 }),
  ];
}

/* ─── Kindness Wall ──────────────────────────────────────────────────── */
/**
 * Mirrors apps.kindness_wall.serializers.KindnessListingListSerializer.
 * Note: backend listing_type is one of 'need_help' | 'offer_help' (see
 * apps.kindness_wall.choices.ListingType). UI normalises to 'need' | 'offer'.
 */
type ApiKindnessCategory = {
  slug: string; title: string;
  icon?: string;
  published_listings_count?: number;
};
type ApiListing = {
  id?: string | number;
  slug: string;
  listing_type: 'need_help' | 'offer_help' | 'need' | 'offer';
  title: string;
  category?: { slug?: string; title?: string; icon?: string };
  province?: string; city?: string; district?: string;
  owner_full_name_snapshot?: string;
  owner_avatar_snapshot?: string;
  cover_image?: string | null;
  published_at?: string;
  expires_at?: string | null;
  view_count?: number;
  bookmark_count?: number;
};

export async function loadKindnessListings(): Promise<KindListing[]> {
  const data = await safeApiFetch<Paginated<ApiListing>>(
    '/kindness-wall/listings/?page_size=18&ordering=-published_at',
    { revalidate: 180, tags: ['kindness'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.map((l) => ({
      slug: l.slug,
      title: l.title,
      // Normalise backend's '*_help' enum into the compact UI variant
      type: (l.listing_type === 'need_help' || l.listing_type === 'need') ? 'need' : 'offer',
      categoryTitle: l.category?.title,
      categorySlug: l.category?.slug,
      province: l.province,
      city: l.city,
      district: l.district,
      ownerName: l.owner_full_name_snapshot,
      ownerAvatar: l.owner_avatar_snapshot,
      coverImage: l.cover_image ?? undefined,
      publishedAt: l.published_at,
      expiresAt: l.expires_at ?? undefined,
      viewCount: l.view_count,
      bookmarkCount: l.bookmark_count,
    }));
  }
  // Seed (fallback) — 12 listings: 6 need + 6 offer (each filter shows 2 rows of 3)
  const now = Date.now();
  const days = (d: number) => new Date(now + d * 24 * 3600 * 1000).toISOString();
  return [
    { slug: 'k-1',  title: 'نیازمند یخچال نو یا دست‌دوم سالم برای خانواده محترم پنج‌نفره',         type: 'need',  categoryTitle: 'لوازم خانگی',   categorySlug: 'home',     city: 'تهران',   province: 'تهران',          ownerName: 'فاطمه ع.',         publishedAt: new Date(now - 1000 * 60 * 30).toISOString(),     expiresAt: days(5),  viewCount: 248,  bookmarkCount: 18, matchesCount: 3 },
    { slug: 'k-2',  title: 'آماده اهدای کتاب‌های درسی مقاطع راهنمایی و دبیرستان',                  type: 'offer', categoryTitle: 'لوازم آموزشی', categorySlug: 'edu',      city: 'مشهد',   province: 'خراسان رضوی',    ownerName: 'حسن م.',           publishedAt: new Date(now - 1000 * 60 * 60 * 2).toISOString(),  expiresAt: days(20), viewCount: 184,  bookmarkCount: 9 },
    { slug: 'k-3',  title: 'درخواست کمک هزینه درمان بیماری خاص فرزند خانواده کم‌بضاعت',           type: 'need',  categoryTitle: 'سلامت و درمان', categorySlug: 'health',   city: 'اصفهان', province: 'اصفهان',         ownerName: 'محمد ر.',          publishedAt: new Date(now - 1000 * 60 * 60 * 6).toISOString(),  expiresAt: days(2),  viewCount: 1245, bookmarkCount: 87, matchesCount: 5 },
    { slug: 'k-4',  title: 'اهدای پوشاک نو زمستانی برای کودکان ۳ تا ۸ سال مناطق محروم',             type: 'offer', categoryTitle: 'پوشاک',         categorySlug: 'clothes',  city: 'شیراز',  province: 'فارس',           ownerName: 'گروه خادمان',      publishedAt: new Date(now - 1000 * 60 * 60 * 12).toISOString(), expiresAt: days(30), viewCount: 92,   bookmarkCount: 12 },
    { slug: 'k-5',  title: 'استخدام کمک‌فروشنده پاره‌وقت برای مغازه لوازم خانگی',                 type: 'need',  categoryTitle: 'فرصت شغلی',     categorySlug: 'jobs',     city: 'تبریز',  province: 'آذربایجان شرقی', ownerName: 'بازرگانی شهاب',    publishedAt: new Date(now - 1000 * 60 * 60 * 24).toISOString(), expiresAt: days(14), viewCount: 312,  bookmarkCount: 23 },
    { slug: 'k-6',  title: 'ارائه مشاوره حقوقی رایگان برای خانواده‌های نیازمند',                  type: 'offer', categoryTitle: 'خدمات تخصصی',  categorySlug: 'services', city: 'قم',     province: 'قم',             ownerName: 'وکیل سلیمی',       publishedAt: new Date(now - 1000 * 60 * 60 * 36).toISOString(), expiresAt: days(45), viewCount: 567,  bookmarkCount: 41, matchesCount: 2 },
    { slug: 'k-7',  title: 'نیاز فوری به ویلچر و تجهیزات پزشکی برای جانباز عزیز',                 type: 'need',  categoryTitle: 'سلامت و درمان', categorySlug: 'health',   city: 'کرج',    province: 'البرز',          ownerName: 'حمید س.',          publishedAt: new Date(now - 1000 * 60 * 60 * 48).toISOString(), expiresAt: days(7),  viewCount: 421,  bookmarkCount: 28 },
    { slug: 'k-8',  title: 'اهدای میز و صندلی اداری نو برای دفاتر مؤسسات خیریه',                  type: 'offer', categoryTitle: 'تجهیزات اداری', categorySlug: 'office',   city: 'تهران',  province: 'تهران',          ownerName: 'شرکت پارس‌تجهیز',   publishedAt: new Date(now - 1000 * 60 * 60 * 60).toISOString(), expiresAt: days(60), viewCount: 137,  bookmarkCount: 7 },
    { slug: 'k-9',  title: 'نیازمند بسته‌های ارزاق ماه مبارک رمضان برای ۲۰ خانواده محروم',         type: 'need',  categoryTitle: 'مواد غذایی',    categorySlug: 'food',     city: 'اهواز',  province: 'خوزستان',        ownerName: 'هیئت ابوالفضل',    publishedAt: new Date(now - 1000 * 60 * 60 * 72).toISOString(), expiresAt: days(12), viewCount: 856,  bookmarkCount: 64, matchesCount: 8 },
    { slug: 'k-10', title: 'ارائه کلاس آموزش رایگان زبان انگلیسی برای دانش‌آموزان مقطع متوسطه',     type: 'offer', categoryTitle: 'آموزش',         categorySlug: 'edu',      city: 'رشت',    province: 'گیلان',          ownerName: 'استاد رحیمی',      publishedAt: new Date(now - 1000 * 60 * 60 * 84).toISOString(), expiresAt: days(40), viewCount: 298,  bookmarkCount: 19 },
    { slug: 'k-11', title: 'نیاز به کمک هزینه جهیزیه برای خانواده زوج جوان جانباز',               type: 'need',  categoryTitle: 'لوازم خانگی',   categorySlug: 'home',     city: 'یزد',    province: 'یزد',            ownerName: 'مادر شهید رضایی',  publishedAt: new Date(now - 1000 * 60 * 60 * 96).toISOString(), expiresAt: days(18), viewCount: 712,  bookmarkCount: 53, matchesCount: 1 },
    { slug: 'k-12', title: 'پیشنهاد رایگان خدمات تعمیرات لوازم خانگی برای خانواده‌های کم‌بضاعت',    type: 'offer', categoryTitle: 'خدمات فنی',     categorySlug: 'services', city: 'کرمان',  province: 'کرمان',          ownerName: 'تعمیرگاه برادران', publishedAt: new Date(now - 1000 * 60 * 60 * 108).toISOString(), expiresAt: days(50), viewCount: 184,  bookmarkCount: 11 },
  ];
}

/* ─── Tabyin ─────────────────────────────────────────────────────────── */
/**
 * Mirrors apps.tabyin.serializers.PublicTabyinContentListSerializer
 * + apps.tabyin.serializers.TabyinAttachmentSerializer (nested).
 *
 * Public list fields:
 *   external_id, title, description, author_username, origin,
 *   source_created_at, source_url, primary_media_type,
 *   attachments[]: { id, url, media_type, size, duration, file_size, title, order }
 */
type ApiTabyinAttachment = {
  id?: number;
  url: string;
  media_type?: 'image' | 'video' | 'audio' | 'other';
  size?: string;
  duration?: number;
  file_size?: number;
  title?: string;
  order?: number;
};
type ApiTabyin = {
  external_id: string;
  title?: string;
  description?: string;
  author_username?: string;
  origin?: 'external' | 'user_submitted';
  source_created_at?: string;
  source_url?: string;
  primary_media_type?: 'image' | 'video' | 'audio' | 'other';
  attachments?: ApiTabyinAttachment[];
};

export async function loadTabyinItems(): Promise<TabyinItem[]> {
  const data = await safeApiFetch<Paginated<ApiTabyin>>(
    '/tabyin/contents/?page_size=12', { revalidate: 180, tags: ['tabyin'] },
  );
  const list = unwrap(data);
  if (list.length) {
    return list.slice(0, 12).map((t, i) => {
      // The first non-other attachment is the canonical cover
      const cover = (t.attachments ?? []).find((a) => a.url) ?? null;
      const dur   = (t.attachments ?? []).find((a) => a.duration)?.duration;
      return {
        id: t.external_id,
        slug: t.external_id,
        title: t.title,
        summary: t.description,
        coverUrl: cover?.url,
        variant: cover ? 'cover' : 'quote',
        mediaType: t.primary_media_type ?? 'image',
        durationSeconds: dur,
        origin: t.origin,
        authorName: t.author_username,
        // Variable height for editorial masonry rhythm — every 3rd & 7th tile tall
        tall: i % 4 === 0 || i % 7 === 0,
      };
    });
  }
  // ── Seed: 24 tiles → exactly 2 pager pages of 12, each laid out on
  //   the fixed 4×4 row grid (4 tall + 8 short) the section enforces.
  //   - quote variant is dropped into one slot per page so every page
  //     has a text card to break the visual rhythm.
  //   - video tiles get a duration so the play affordance + media badge
  //     light up; audio tiles get a duration too.
  //   - 2 user-submitted tiles per page so the 'مردمی' chip is visible.
  const tones: Array<[string, string]> = [
    // page 1
    ['#3FA797', '#0A6E64'], ['#0D8074', '#053832'], ['#3FA797', '#155F55'],
    ['#5DB3A4', '#0A6E64'], ['#0D8074', '#0A6E64'], ['#3FA797', '#053832'],
    ['#5DB3A4', '#0D8074'], ['#0A6E64', '#053832'], ['#3FA797', '#085C54'],
    ['#5DB3A4', '#085C54'], ['#0D8074', '#085C54'], ['#3FA797', '#0A6E64'],
    // page 2
    ['#2FA08D', '#053832'], ['#155F55', '#0A6E64'], ['#5DB3A4', '#053832'],
    ['#3FA797', '#0A6E64'], ['#0A6E64', '#085C54'], ['#0D8074', '#155F55'],
    ['#5DB3A4', '#155F55'], ['#3FA797', '#0D8074'], ['#0D8074', '#053832'],
    ['#5DB3A4', '#0A6E64'], ['#3FA797', '#053832'], ['#0A6E64', '#0D8074'],
  ];
  const titles = [
    // page 1
    'دهه‌ی فجر انقلاب اسلامی',
    'منبر انقلاب اسلامی',
    '«جلادها میان ما»',
    'حضرت معصومه (س)',
    '',                       // quote tile #1
    'هنر مسلح مقاومت',
    'کبوتر صلح',
    'دفاع از وطن',
    'ریشه در تاریخ',
    'نسل سوم انقلاب',
    'به یاد شهدا',
    'لاإله إلا الله',
    // page 2
    'راه ادامه دارد',
    'پای سفره‌ی شهدا',
    'پرچم همیشه برافراشته',
    '',                       // quote tile #2
    'صدای مقاومت',
    'تصویر آرامش',
    'مادران چشم‌انتظار',
    'گلستان عاشقان',
    'یاران ناشناخته',
    'تا فردای پیروزی',
    'پاسبانان غیرت',
    'روایت یک قهرمان',
  ];
  const quotes = [
    'او به خاطر نقاشی‌های واقع‌گرایانه‌اش از رویدادهای مذهبی شهرت دارد. خالق آثاری چون «عرش بر زمین افتاد»، «شیرین‌تر از عسل» و «آخرین سرباز لشکر» است.',
    'هنرِ مقاومت، روایتِ صادقِ مردمی است که در سکوتِ تاریخ، صدای حقیقت را با قلم و قلم‌مو نگه داشتند تا نسل‌های آینده بدانند که اینجا چه گذشت.',
  ];
  // index → quote payload mapping
  const quoteAt: Record<number, string> = { 4: quotes[0], 15: quotes[1] };
  const videoAt = new Set([1, 9, 13, 22]);
  const audioAt = new Set([11, 19]);
  const userAt  = new Set([7, 10, 18, 23]);

  return tones.map((t, i) => {
    const isQuote = i in quoteAt;
    const isVideo = videoAt.has(i);
    const isAudio = audioAt.has(i);
    return {
      id: `seed-${i}`,
      slug: `seed-${i}`,
      title: titles[i] || undefined,
      summary: isQuote ? quoteAt[i] : undefined,
      variant: isQuote ? 'quote' : undefined,
      // 'tall' is left off here — TabyinSection forces the canonical
      // tall pattern (positions 0, 5, 8 of each page). This keeps the
      // grid stable on every page flip.
      mediaType: isQuote ? 'image' : isVideo ? 'video' : isAudio ? 'audio' : 'image',
      durationSeconds: isVideo ? 95 + (i % 6) * 30 : isAudio ? 240 + (i % 4) * 60 : undefined,
      origin: userAt.has(i) ? 'user_submitted' : 'external',
      authorName: userAt.has(i) ? 'کاربر مردمی' : undefined,
      toneFrom: t[0], toneTo: t[1],
    };
  });
}
