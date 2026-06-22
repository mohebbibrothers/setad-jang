/**
 * Server-side data loaders for the homepage.
 *
 * Production policy:
 *   Every loader hits its Django backend endpoint and returns ONLY real
 *   data. When the backend is unreachable or returns an empty list, the
 *   loader returns []  — the sections then render their own empty
 *   state. No demo / seed / mock content is ever shipped to production.
 *
 * Backend contracts (mirror config/urls.py and apps/*):
 *   GET /api/v1/madadkar/campaigns/         → CampaignPublicListSerializer
 *   GET /api/v1/r4j/criminals/              → R4JPublicCriminalListSerializer
 *   GET /api/v1/lms/categories/             → LMSCategoryPublicSerializer
 *   GET /api/v1/lms/courses/                → CourseSummarySerializer
 *   GET /api/v1/kindness-wall/categories/   → KindnessCategorySerializer
 *   GET /api/v1/kindness-wall/listings/     → KindnessListingListSerializer
 *   GET /api/v1/tabyin/contents/            → PublicTabyinContentListSerializer
 *   GET /api/v1/public-reports/subjects/    → ReportSubjectPublicSerializer
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
 * Mirrors apps.madadkar.serializers.CampaignPublicListSerializer.
 * Monetary fields are stored in TOMAN; the UI multiplies by 10 to render
 * Rial as required by the designer.
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
  participant_count?: number;
  has_deadline?: boolean;
  deadline?: string | null;
  status?: string;
  status_display?: string;
  published_at?: string | null;
  /** Detail / admin endpoints embed the gallery; list endpoint does not. */
  gallery_images?: Array<{
    id: number;
    image: string;
    alt_text?: string;
    display_order?: number;
  }>;
};

export async function loadCampaigns(): Promise<CampaignCard[]> {
  // 8 cards = exactly 2 pager pages of 4 on desktop.  Newest first.
  const data = await safeApiFetch<Paginated<ApiCampaign>>(
    '/madadkar/campaigns/?page_size=8&ordering=-published_at',
    { revalidate: 300, tags: ['campaigns'] },
  );
  const list = unwrap(data);
  return list.map((c) => ({
    slug: c.slug,
    title: c.title,
    sponsor: c.sponsor?.name || 'گروه جهادی',
    sponsorLogo: c.sponsor?.logo ?? undefined,
    totalAmount: c.total_amount ?? 0,
    sharePrice: c.share_price ?? (c.total_amount && c.total_shares
      ? Math.floor(c.total_amount / c.total_shares) : 0),
    sharesTotal: c.total_shares ?? 0,
    sharesRemaining: c.remaining_shares ?? Math.max(
      0, (c.total_shares ?? 0) - (c.purchased_shares ?? 0),
    ),
    progressPercent: c.progress_percent ?? 0,
    coverUrl: c.cover_image ?? undefined,
    participantCount: c.participant_count,
    isFullyFunded: c.is_fully_funded,
    hasDeadline: c.has_deadline,
    deadline: c.deadline ?? undefined,
    statusDisplay: c.status_display,
    gallery: (c.gallery_images ?? [])
      .slice()
      .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
      .map((g) => ({ url: g.image, alt: g.alt_text || c.title })),
  }));
}

/* ─── R4J ────────────────────────────────────────────────────────────── */
type ApiCriminalPhoto = { id: number; image: string };
type ApiCriminal = {
  id?: number;
  slug: string;
  first_name?: string;
  last_name?: string;
  country?: string;
  province?: string;
  city?: string;
  primary_photo?: ApiCriminalPhoto | null;
  total_bounty_toman?: number;
  bounties_count?: number;
};
export async function loadCriminals(): Promise<CriminalCard[]> {
  const data = await safeApiFetch<Paginated<ApiCriminal>>(
    '/r4j/criminals/?page_size=8&ordering=-total_bounty_toman',
    { revalidate: 600, tags: ['criminals'] },
  );
  const list = unwrap(data);
  return list.map((p) => {
    const fullName = [p.first_name, p.last_name].filter(Boolean).join(' ').trim() || p.slug;
    return {
      slug: p.slug,
      fullName,
      imageUrl: p.primary_photo?.image ?? undefined,
      pillLabel: [p.city, p.province, p.country].filter(Boolean).join('، ') || undefined,
      totalBounty: p.total_bounty_toman,
      bountiesCount: p.bounties_count,
    };
  });
}

/* ─── LMS ────────────────────────────────────────────────────────────── */
type ApiLmsCategory = { slug: string; title: string; courses_count?: number };
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
    '/lms/categories/?page_size=20',
    { revalidate: 600, tags: ['lms-categories'] },
  );
  const list = unwrap(data);
  return list.map((c) => ({ slug: c.slug, title: c.title, count: c.courses_count }));
}

export async function loadCourses(): Promise<CourseCard[]> {
  const data = await safeApiFetch<Paginated<ApiCourse>>(
    '/lms/courses/?page_size=12&ordering=-published_at',
    { revalidate: 300, tags: ['courses'] },
  );
  const list = unwrap(data);
  return list.map((c) => ({
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
  }));
}

/* ─── Kindness Wall ──────────────────────────────────────────────────── */
type ApiKindness = {
  id?: number;
  slug: string;
  listing_type: 'need_help' | 'offer_help';
  category?: { id?: number; slug?: string; title?: string; icon?: string };
  title: string;
  province?: string;
  city?: string;
  district?: string;
  owner_full_name_snapshot?: string;
  owner_avatar_snapshot?: string | null;
  published_at?: string;
  expires_at?: string | null;
  view_count?: number;
  cover_image?: string | null;
  description?: string;
  /** Detail endpoint embeds full images + matches count when available. */
  images?: Array<{ id: number; image: string; alt_text?: string; caption?: string; is_cover?: boolean; order?: number }>;
  matches_count?: number;
  bookmark_count?: number;
};
export async function loadKindnessListings(): Promise<KindListing[]> {
  const data = await safeApiFetch<Paginated<ApiKindness>>(
    '/kindness-wall/listings/?page_size=12&ordering=-published_at',
    { revalidate: 240, tags: ['kindness'] },
  );
  const list = unwrap(data);
  return list.map((l) => ({
    slug: l.slug,
    title: l.title,
    type: l.listing_type === 'need_help' ? 'need' : 'offer',
    categoryTitle: l.category?.title,
    categorySlug: l.category?.slug,
    province: l.province,
    city: l.city,
    district: l.district,
    ownerName: l.owner_full_name_snapshot,
    ownerAvatar: l.owner_avatar_snapshot ?? undefined,
    coverImage: l.cover_image ?? undefined,
    publishedAt: l.published_at,
    expiresAt: l.expires_at ?? undefined,
    viewCount: l.view_count,
    bookmarkCount: l.bookmark_count,
    matchesCount: l.matches_count,
    gallery: (l.images ?? [])
      .slice()
      .sort((a, b) => {
        if (!!b.is_cover !== !!a.is_cover) return b.is_cover ? 1 : -1;
        return (a.order ?? 0) - (b.order ?? 0);
      })
      .map((g) => ({ url: g.image, alt: g.alt_text || g.caption || l.title })),
  }));
}

/* ─── Tabyin ─────────────────────────────────────────────────────────── */
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
    '/tabyin/contents/?page_size=20&ordering=-source_created_at',
    { revalidate: 180, tags: ['tabyin'] },
  );
  const list = unwrap(data);
  return list.map((t) => {
    const cover = (t.attachments ?? []).find((a) => a.media_type === 'image' && a.url)
      ?? (t.attachments ?? []).find((a) => a.url);
    const videoOrAudio = (t.attachments ?? []).find((a) => a.duration);
    return {
      id: t.external_id,
      slug: t.external_id,
      title: t.title,
      summary: t.description,
      coverUrl: cover?.url,
      variant: cover ? 'cover' : 'quote',
      mediaType: t.primary_media_type ?? 'image',
      durationSeconds: videoOrAudio?.duration,
      origin: t.origin,
      authorName: t.author_username,
      sourceUrl: t.source_url,
    };
  });
}

/* ─── Public Reports ─────────────────────────────────────────────────── */
type ApiReportSubject = { id: number; title: string; slug?: string; description?: string; order?: number };

export type ReportSubject = { id: string; name: string; description?: string };

export async function loadReportSubjects(): Promise<ReportSubject[]> {
  const data = await safeApiFetch<Paginated<ApiReportSubject>>(
    '/public-reports/subjects/?page_size=20',
    { revalidate: 600, tags: ['report-subjects'] },
  );
  const list = unwrap(data);
  return list.map((s) => ({
    id: String(s.id),
    name: s.title,
    description: s.description,
  }));
}
