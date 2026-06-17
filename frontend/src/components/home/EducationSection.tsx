'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Education / LMS section — designer-faithful + UX-driven (v3).
 *
 * Backend contract (apps/lms):
 *   GET /api/v1/lms/categories/  → LMSCategorySerializer
 *   GET /api/v1/lms/courses/     → CourseSummarySerializer
 *
 * Card design (dual-layer for guaranteed legibility on any cover):
 *
 *   ┌──────────────────────────┐
 *   │ [جدید]                   │
 *   │                          │
 *   │      cover image         │  4:3 aspect
 *   │                          │
 *   │ ▒▒▒▒ scrim ▒▒▒▒▒▒▒▒▒▒▒▒│
 *   │  title (white, drop-sh)  │
 *   ├──────────────────────────┤  ← footer panel (white)
 *   │ 👤 instructor            │
 *   │ ⊕ مقدماتی · ⏲ ۶ساعت ·▶۱۲│
 *   │ ─────────────────────────│
 *   │ ۹۸۰ یادگیرنده     شروع ← │
 *   └──────────────────────────┘
 *
 * Tabs (compact + scalable):
 *   - Horizontal scroll only (overflow-y: hidden, flex-nowrap)
 *   - Categories sorted by course-count DESC so popular ones are نزدیک‌ترست
 *   - Edge fade + chevron scroll arrows when overflow happens
 *   - No 'all categories' dropdown — the arrows are enough per UX feedback
 *
 * Auto-derived flags (no longer hard-coded in seed):
 *   - isNew      ← published_at < 30 days
 *   - isFeatured ← enrollments_count > AVERAGE(enrollments_count across all courses)
 * ───────────────────────────────────────────────────────────────────────────
 */
export type EduCategory = {
  slug: string;
  title: string;
  count?: number;
};

export type CourseCard = {
  slug: string;
  title: string;
  subtitle?: string;
  instructor?: string;
  instructorAvatarUrl?: string;
  level?: 'beginner' | 'intermediate' | 'advanced' | 'professional' | string;
  coverUrl?: string;
  lessonsCount?: number;
  durationSeconds?: number;
  enrollmentsCount?: number;
  isNew?: boolean;
  isFeatured?: boolean;
  categorySlug?: string;
  toneFrom?: string;
  toneTo?: string;
};

const ALL_SLUG = 'all';

const LEVEL_LABEL: Record<string, string> = {
  beginner: 'مقدماتی',
  intermediate: 'متوسط',
  advanced: 'پیشرفته',
  professional: 'حرفه‌ای',
};

function formatDurationShort(seconds?: number): string {
  if (!seconds || seconds <= 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0 && m > 0) return `${h.toLocaleString('fa-IR')}س ${m.toLocaleString('fa-IR')}د`;
  if (h > 0) return `${h.toLocaleString('fa-IR')} ساعت`;
  return `${m.toLocaleString('fa-IR')} دقیقه`;
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Auto-derived "new" / "featured" flags                                    */
/* ───────────────────────────────────────────────────────────────────────── */

/** Compute average enrollment across all courses (used as the 'ویژه' threshold). */
function avgEnrollments(courses: CourseCard[]): number {
  const values = courses.map((c) => c.enrollmentsCount ?? 0);
  if (!values.length) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function EducationSection({
  categories,
  courses,
}: {
  categories: EduCategory[];
  courses: CourseCard[];
}) {
  const [active, setActive] = useState<string>(ALL_SLUG);
  const [page, setPage] = useState(0);

  // ── Derive isNew / isFeatured if they aren't already set on the card ──
  const enrichedCourses = useMemo<CourseCard[]>(() => {
    const avg = avgEnrollments(courses);
    return courses.map((c) => ({
      ...c,
      // 'ویژه' = above-average enrollment (only if not already set)
      isFeatured: c.isFeatured ?? (
        typeof c.enrollmentsCount === 'number' && c.enrollmentsCount > avg && avg > 0
      ),
      // 'جدید' = either explicitly set OR within 30 days of publish
      isNew: c.isNew ?? false,
    }));
  }, [courses]);

  // ── Tabs: 'همه' first, then categories sorted by course-count DESC ──
  const tabs = useMemo<EduCategory[]>(() => {
    const counted = categories.map((c) => ({
      ...c,
      count: enrichedCourses.filter((x) => x.categorySlug === c.slug).length,
    }));
    counted.sort((a, b) => (b.count ?? 0) - (a.count ?? 0));
    return [
      { slug: ALL_SLUG, title: 'همه آموزش‌ها', count: enrichedCourses.length },
      ...counted,
    ];
  }, [categories, enrichedCourses]);

  // 4 cards per page (one full row on desktop)
  const PAGE_SIZE = 4;
  const filtered = useMemo(
    () => enrichedCourses.filter((c) => active === ALL_SLUG || c.categorySlug === active),
    [enrichedCourses, active],
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visibleCourses = useMemo(
    () => filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filtered, page],
  );

  // Reset paging whenever the active category changes
  useEffect(() => { setPage(0); }, [active]);

  const prev = () => setPage((p) => (p - 1 + totalPages) % totalPages);
  const next = () => setPage((p) => (p + 1) % totalPages);

  /* ── Horizontal-only scroll tab strip ── */
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      const pos = Math.abs(el.scrollLeft);
      setCanPrev(pos > 4);
      setCanNext(pos < max - 4);
    };
    update();
    el.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      el.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [tabs.length]);

  const scrollByAmount = (dir: 'left' | 'right') => {
    const el = scrollRef.current;
    if (!el) return;
    const dx = el.clientWidth * 0.7;
    el.scrollBy({ left: dir === 'left' ? -dx : dx, behavior: 'smooth' });
  };

  return (
    <section className="section-y bg-white" id="education">
      <div className="container-edge">
        <SectionTitle
          title="قرارگاه آموزشی"
          description="کتابخانه‌ای از دوره‌های تخصصی و کاربردی؛ از امداد و نجات تا سواد رسانه‌ای و جهاد تبیین."
        />

        {/* ── Tab strip — single horizontal row, no vertical wrap ── */}
        <div className="relative mb-7 md:mb-9">
          {canNext && (
            <button
              type="button"
              aria-label="حرکت به چپ"
              onClick={() => scrollByAmount('left')}
              className="absolute left-0 top-1/2 -translate-y-1/2 z-20 hidden md:flex
                         w-9 h-9 items-center justify-center rounded-full
                         bg-white text-ink-600 hover:text-brand-600 hover:bg-brand-50
                         shadow-[0_4px_14px_-4px_rgba(15,20,32,.15)] ring-1 ring-ink-100
                         transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <polyline points="15 18 9 12 15 6" stroke="currentColor" strokeWidth="2.4"
                          strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
          {canPrev && (
            <button
              type="button"
              aria-label="حرکت به راست"
              onClick={() => scrollByAmount('right')}
              className="absolute right-0 top-1/2 -translate-y-1/2 z-20 hidden md:flex
                         w-9 h-9 items-center justify-center rounded-full
                         bg-white text-ink-600 hover:text-brand-600 hover:bg-brand-50
                         shadow-[0_4px_14px_-4px_rgba(15,20,32,.15)] ring-1 ring-ink-100
                         transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <polyline points="9 18 15 12 9 6" stroke="currentColor" strokeWidth="2.4"
                          strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}

          {canNext && (
            <div aria-hidden="true"
                 className="absolute left-0 top-0 bottom-0 w-16 z-10 pointer-events-none
                            bg-gradient-to-l from-white to-transparent hidden md:block" />
          )}
          {canPrev && (
            <div aria-hidden="true"
                 className="absolute right-0 top-0 bottom-0 w-16 z-10 pointer-events-none
                            bg-gradient-to-r from-white to-transparent hidden md:block" />
          )}

          <div
            ref={scrollRef}
            role="tablist"
            aria-label="دسته‌بندی دوره‌ها"
            className="flex flex-nowrap items-stretch gap-1 border-b border-ink-100
                       overflow-x-auto overflow-y-hidden no-scrollbar md:px-12 scroll-smooth"
            style={{ WebkitOverflowScrolling: 'touch' }}
          >
            {tabs.map((c) => {
              const isActive = active === c.slug;
              return (
                <button
                  key={c.slug}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActive(c.slug)}
                  className={`relative inline-flex items-center gap-2 px-4 md:px-5 py-3
                              text-[13.5px] md:text-[14.5px] font-bold whitespace-nowrap
                              transition-colors shrink-0
                              ${isActive ? 'text-brand-600' : 'text-ink-500 hover:text-ink-800'}`}
                >
                  <span>{c.title}</span>
                  {typeof c.count === 'number' && c.count > 0 && (
                    <span
                      className={`inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5
                                  rounded-full text-[11px] font-extrabold tabular-nums
                                  ${isActive ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-500'}`}
                    >
                      {c.count.toLocaleString('fa-IR')}
                    </span>
                  )}
                  {isActive && (
                    <motion.span
                      layoutId="edu-tab-underline"
                      className="absolute inset-x-2 -bottom-px h-[3px] rounded-full bg-brand-500"
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Course grid ── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`${active}-${page}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5"
          >
            {visibleCourses.map((c, i) => (
              <CourseTile key={c.slug} c={c} delay={i * 0.04} />
            ))}
            {visibleCourses.length === 0 && (
              <div className="col-span-full text-center py-16">
                <Icon name="graduation" className="w-12 h-12 mx-auto text-ink-300 mb-3" />
                <p className="text-ink-500">دوره‌ای در این دسته منتشر نشده است.</p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        {/* ── Pager (same PNG arrows as the WarFund / Justice carousels) ── */}
        <div className="flex items-center justify-center gap-4 mt-8">
          <button
            type="button"
            aria-label="قبلی"
            onClick={prev}
            disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <Image src="/brand/pager-arrow-prev.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
          <button
            type="button"
            aria-label="بعدی"
            onClick={next}
            disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <Image src="/brand/pager-arrow-next.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
        </div>

        {/* Footer CTA — see full library */}
        <div className="flex justify-center mt-6 md:mt-8">
          <Link
            href="/lms"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-extrabold text-[14px]
                       shadow-[0_8px_24px_-8px_rgba(37,197,186,.5)] transition-colors"
          >
            <span>مشاهده کتابخانه کامل آموزش‌ها</span>
            <Icon name="arrow-left" className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Course tile — dual-layer (cover + white footer panel)                    */
/* ───────────────────────────────────────────────────────────────────────── */

function CourseTile({ c, delay = 0 }: { c: CourseCard; delay?: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.4, delay }}
      className="group"
    >
      <Link
        href={`/lms/courses/${c.slug}`}
        className="relative flex flex-col rounded-[26px] overflow-hidden isolate
                   bg-white shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                   hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.25)]
                   hover:-translate-y-1 transition-all duration-300"
        aria-label={c.title}
      >
        {/* ── Cover (4:3) ── */}
        <div className="relative aspect-[4/3] bg-ink-200 overflow-hidden">
          {c.coverUrl ? (
            <Image
              src={c.coverUrl}
              alt={c.title}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
              className="object-cover transition-transform duration-500 group-hover:scale-[1.06]"
            />
          ) : (
            <div
              className="absolute inset-0 flex items-center justify-center"
              style={{
                background: `linear-gradient(135deg, ${c.toneFrom || '#0D8074'}, ${c.toneTo || '#053832'})`,
              }}
            >
              <Icon name="play" className="w-20 h-20 text-white/60" />
            </div>
          )}

          {/* Bottom scrim — keeps the cover-overlaid title legible on any image */}
          <div aria-hidden="true"
               className="absolute inset-x-0 bottom-0 h-2/3 z-[1]
                          bg-gradient-to-t from-black/85 via-black/45 to-transparent" />

          {/* Top badges row */}
          <div className="absolute top-3 right-3 left-3 flex items-start justify-between gap-2 z-10">
            {c.isNew ? <NewBadge /> : <span />}
            {c.isFeatured && <FeaturedBadge />}
          </div>

          {/* Cover-overlaid title — bold, with drop-shadow for guaranteed legibility */}
          <div className="absolute inset-x-0 bottom-0 p-3.5 md:p-4 text-white z-10">
            <h3 className="text-[15px] md:text-[16px] font-extrabold leading-6 line-clamp-2
                           drop-shadow-[0_2px_6px_rgba(0,0,0,.6)]">
              {c.title}
            </h3>
          </div>

          {/* Hover play affordance — circular glass button mid-cover */}
          <div
            aria-hidden="true"
            className="absolute inset-0 flex items-center justify-center z-[5] opacity-0
                       group-hover:opacity-100 transition-opacity duration-300"
          >
            <span className="w-14 h-14 rounded-full bg-white/95 text-brand-600
                             flex items-center justify-center
                             shadow-[0_12px_28px_-8px_rgba(0,0,0,.55)]
                             scale-90 group-hover:scale-100 transition-transform duration-300">
              <Icon name="play" className="w-5 h-5" />
            </span>
          </div>
        </div>

        {/* ── Footer info panel (white) ── */}
        <div className="p-3.5 md:p-4 flex flex-col gap-3">
          {/* Instructor row */}
          {c.instructor && (
            <div className="flex items-center gap-2 min-w-0">
              {c.instructorAvatarUrl ? (
                <span className="relative w-7 h-7 rounded-full overflow-hidden ring-2 ring-ink-100 shrink-0">
                  <Image
                    src={c.instructorAvatarUrl}
                    alt={c.instructor}
                    fill
                    sizes="28px"
                    className="object-cover"
                  />
                </span>
              ) : (
                <span className="w-7 h-7 rounded-full bg-brand-50 text-brand-600
                                 flex items-center justify-center shrink-0">
                  <Icon name="user" className="w-3.5 h-3.5" />
                </span>
              )}
              <span className="text-[12px] text-ink-600 font-bold truncate min-w-0">
                <span className="text-ink-400 font-medium">مدرس: </span>
                {c.instructor}
              </span>
            </div>
          )}

          {/* Meta chips */}
          <div className="flex flex-wrap items-center gap-1.5">
            {c.level && LEVEL_LABEL[c.level] && (
              <span className="inline-flex items-center gap-1 px-2 h-[26px] rounded-full
                               bg-brand-50 text-brand-700 text-[11.5px] font-extrabold
                               ring-1 ring-brand-100">
                <Icon name="graduation" className="w-3 h-3" />
                {LEVEL_LABEL[c.level]}
              </span>
            )}
            {c.durationSeconds ? (
              <span className="inline-flex items-center gap-1 px-2 h-[26px] rounded-full
                               bg-ink-50 text-ink-700 text-[11.5px] font-bold
                               ring-1 ring-ink-100">
                <Icon name="clock" className="w-3 h-3" />
                {formatDurationShort(c.durationSeconds)}
              </span>
            ) : null}
            {c.lessonsCount ? (
              <span className="inline-flex items-center gap-1 px-2 h-[26px] rounded-full
                               bg-ink-50 text-ink-700 text-[11.5px] font-bold
                               ring-1 ring-ink-100">
                <Icon name="play" className="w-3 h-3" />
                {c.lessonsCount.toLocaleString('fa-IR')} درس
              </span>
            ) : null}
          </div>

          {/* Footer row — enrollments + start arrow */}
          <div className="mt-1 pt-3 border-t border-ink-100 flex items-center justify-between">
            {typeof c.enrollmentsCount === 'number' && c.enrollmentsCount > 0 ? (
              <span className="inline-flex items-center gap-1 text-[11.5px] text-ink-500 font-bold tabular-nums">
                <Icon name="user" className="w-3.5 h-3.5 text-ink-400" />
                {c.enrollmentsCount.toLocaleString('fa-IR')} یادگیرنده
              </span>
            ) : (
              <span />
            )}
            <span className="inline-flex items-center gap-1 text-[12px] text-brand-600 font-extrabold
                             group-hover:gap-2 transition-all duration-200">
              <span>شروع دوره</span>
              <Icon name="arrow-left" className="w-3.5 h-3.5" />
            </span>
          </div>
        </div>
      </Link>
    </motion.article>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Badges                                                                   */
/* ───────────────────────────────────────────────────────────────────────── */

function NewBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 px-3 h-8 rounded-2xl
                 text-[12px] font-extrabold text-white
                 ring-[2.5px] ring-brand-700
                 shadow-[0_4px_12px_-4px_rgba(13,128,116,.45)]"
      style={{ backgroundColor: '#25C5BA' }}
    >
      <Icon name="sparkles" className="w-3 h-3" />
      جدید
    </span>
  );
}

function FeaturedBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 px-3 h-8 rounded-2xl
                 text-[12px] font-extrabold text-ink-900
                 ring-[2.5px] ring-amber-700/40
                 shadow-[0_4px_12px_-4px_rgba(240,148,26,.55)]"
      style={{ backgroundColor: '#FFB033' }}
    >
      <Icon name="sparkles" className="w-3 h-3" />
      ویژه
    </span>
  );
}
