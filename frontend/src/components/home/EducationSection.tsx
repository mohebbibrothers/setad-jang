'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Education / LMS section — designer-faithful (v2).
 *
 * Backend contract (apps/lms):
 *   GET /api/v1/lms/categories/  → LMSCategorySerializer
 *     fields: id, title, slug, description, icon, cover_image, order
 *
 *   GET /api/v1/lms/courses/     → CourseSummarySerializer
 *     fields: id, category{...}, title, slug, subtitle, short_description,
 *             instructor_name, level, status, is_featured, cover_image,
 *             lessons_count, estimated_duration_seconds, enrollments_count,
 *             graduates_count, published_at
 *
 * Level enum (apps.lms.choices.CourseLevel):
 *   beginner | intermediate | advanced | professional
 *
 * Layout (matches the latest mockup exactly):
 *
 *   ── همه آموزش‌ها · امداد و نجات · موارد امنیتی · … · همه دسته‌ها ▾ ──
 *
 *   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
 *   │  cover  │  │  cover  │  │  cover  │  │  cover  │
 *   │ [جدید]  │  │ [جدید]  │  │ [جدید]  │  │ [جدید]  │
 *   │         │  │         │  │ ⊙       │  │         │
 *   │  title  │  │  title  │  │  title  │  │  title  │
 *   │ ┃ ⏲ ⓘ  │  │ ┃ ⏲ ⓘ  │  │ ┃ ⏲ ⓘ  │  │ ┃ ⏲ ⓘ  │
 *   └─────────┘  └─────────┘  └─────────┘  └─────────┘
 *                       ◀── ──▶     (designer pager arrows)
 *
 *   Card extras driven by backend fields:
 *     - 'جدید' badge from published_at < 30 days
 *     - 'ویژه' badge from is_featured
 *     - bottom gradient → title + instructor + level pill + lessons/duration
 *     - avatar circle (if instructor_avatar) shown subtly mid-card on hover
 *
 *   Tabs handle ANY number of categories:
 *     - Horizontally scrollable on overflow with hidden scrollbar
 *     - Edge-fade gradients + chevron arrows appear only when scrollable
 *     - A 'همه دسته‌ها ▾' dropdown sits at the strip end as a power-user
 *       fallback so a long taxonomy stays one click away.
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
  /** Gradient fallback when no cover */
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

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0 && m > 0) return `${h.toLocaleString('fa-IR')} ساعت و ${m.toLocaleString('fa-IR')} دقیقه`;
  if (h > 0) return `${h.toLocaleString('fa-IR')} ساعت`;
  return `${m.toLocaleString('fa-IR')} دقیقه`;
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

  // Always prepend the "all" tab with a live count badge
  const tabs = useMemo(() => {
    const all: EduCategory = { slug: ALL_SLUG, title: 'همه آموزش‌ها', count: courses.length };
    return [
      all,
      ...categories.map((c) => ({
        ...c,
        count: courses.filter((x) => x.categorySlug === c.slug).length,
      })),
    ];
  }, [categories, courses]);

  // 4 cards per page (one full row on desktop) — extra pages reached via pager
  const PAGE_SIZE = 4;
  const filtered = useMemo(
    () => courses.filter((c) => active === ALL_SLUG || c.categorySlug === active),
    [courses, active],
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

  /* ── Horizontal-scroll tab strip with edge arrows + dropdown fallback ── */
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      // RTL: scrollLeft is ≤ 0 in most browsers; normalise to a positive offset
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

  // Close the "all categories" dropdown on outside-click
  useEffect(() => {
    if (!menuOpen) return;
    function onDown(e: MouseEvent | TouchEvent) {
      const t = e.target as HTMLElement;
      if (!t.closest('[data-edu-menu]')) setMenuOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown, { passive: true });
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
    };
  }, [menuOpen]);

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

        {/* ── Tab strip ── */}
        <div className="relative mb-7 md:mb-9">
          {/* Edge arrows — only show when content overflows */}
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

          {/* Edge fade gradients */}
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
            className="flex items-stretch gap-1 border-b border-ink-100
                       overflow-x-auto no-scrollbar md:px-12 scroll-smooth"
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

            {/* 'All categories' dropdown — scales when a long taxonomy ships */}
            <div className="relative ms-auto shrink-0 hidden md:flex items-center"
                 data-edu-menu="">
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-[13px] font-extrabold
                            transition-colors
                            ${menuOpen
                              ? 'bg-brand-500 text-white'
                              : 'bg-ink-50 text-ink-700 hover:bg-ink-100'}`}
              >
                <Icon name="grid" className="w-3.5 h-3.5" />
                <span>همه دسته‌ها</span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                     className={`transition-transform duration-300 ${menuOpen ? 'rotate-180' : ''}`}
                     aria-hidden="true">
                  <polyline points="6 9 12 15 18 9" stroke="currentColor" strokeWidth="2.6"
                            strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              <AnimatePresence>
                {menuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.97 }}
                    transition={{ type: 'spring', stiffness: 380, damping: 26, mass: 0.6 }}
                    role="menu"
                    className="absolute top-full left-0 mt-2 min-w-[260px] max-h-[360px] overflow-y-auto
                               bg-white rounded-2xl shadow-[0_24px_60px_-12px_rgba(0,0,0,.25)]
                               ring-1 ring-ink-100 p-2 z-30"
                  >
                    {tabs.map((c) => {
                      const isActive = active === c.slug;
                      return (
                        <button
                          key={c.slug}
                          role="menuitem"
                          onClick={() => { setActive(c.slug); setMenuOpen(false); }}
                          className={`w-full flex items-center justify-between gap-3 px-3 h-10
                                      rounded-xl text-[13px] font-bold transition-colors text-right
                                      ${isActive
                                        ? 'bg-brand-50 text-brand-700'
                                        : 'text-ink-700 hover:bg-ink-50'}`}
                        >
                          <span className="truncate">{c.title}</span>
                          {typeof c.count === 'number' && (
                            <span className={`inline-flex items-center justify-center min-w-[24px] h-[22px]
                                              px-1.5 rounded-full text-[11px] font-extrabold tabular-nums
                                              ${isActive
                                                ? 'bg-brand-500 text-white'
                                                : 'bg-ink-100 text-ink-500'}`}>
                              {(c.count ?? 0).toLocaleString('fa-IR')}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
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
            className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-5"
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
/*  Course tile                                                              */
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
        className="relative block aspect-[4/5] rounded-[26px] overflow-hidden isolate
                   bg-ink-200 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                   hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.25)]
                   hover:-translate-y-1 transition-all duration-300"
        aria-label={c.title}
      >
        {/* Cover */}
        {c.coverUrl ? (
          <Image
            src={c.coverUrl}
            alt={c.title}
            fill
            sizes="(max-width: 768px) 50vw, (max-width: 1024px) 33vw, 25vw"
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

        {/* Bottom gradient overlay — title legibility */}
        <div aria-hidden="true"
             className="absolute inset-x-0 bottom-0 h-[72%]
                        bg-gradient-to-t from-black/80 via-black/35 to-transparent" />

        {/* Top badges */}
        <div className="absolute top-3 right-3 left-3 flex items-start justify-between gap-2 z-10">
          {c.isNew ? <NewBadge /> : <span />}
          {c.isFeatured && <FeaturedBadge />}
        </div>

        {/* Instructor avatar — small circle mid-card on hover */}
        {c.instructorAvatarUrl && (
          <div
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[55%]
                       w-14 h-14 rounded-full overflow-hidden ring-4 ring-white/60
                       shadow-[0_8px_22px_rgba(0,0,0,.45)] opacity-0
                       group-hover:opacity-100 group-hover:scale-100 scale-90
                       transition-all duration-300 z-[5]"
          >
            <Image
              src={c.instructorAvatarUrl}
              alt={c.instructor || ''}
              fill
              sizes="56px"
              className="object-cover"
            />
          </div>
        )}

        {/* Body block — title, instructor, meta row */}
        <div className="absolute inset-x-0 bottom-0 p-3.5 md:p-4 text-white z-10">
          {c.instructor && (
            <p className="text-[11px] md:text-[11.5px] opacity-90 mb-1 line-clamp-1 font-medium">
              <span className="opacity-75">مدرس: </span>
              {c.instructor}
            </p>
          )}
          <h3 className="text-[14px] md:text-[15px] font-extrabold leading-6 line-clamp-2
                         drop-shadow-[0_2px_4px_rgba(0,0,0,.4)]">
            {c.title}
          </h3>

          {/* Meta row — level pill + duration + lessons */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
            {c.level && LEVEL_LABEL[c.level] && (
              <span className="inline-flex items-center gap-1 px-2 h-[22px] rounded-full
                               bg-white/15 backdrop-blur-md ring-1 ring-white/10
                               font-extrabold">
                <Icon name="graduation" className="w-3 h-3" />
                {LEVEL_LABEL[c.level]}
              </span>
            )}
            {c.durationSeconds ? (
              <span className="inline-flex items-center gap-1 px-2 h-[22px] rounded-full
                               bg-white/15 backdrop-blur-md ring-1 ring-white/10
                               font-bold">
                <Icon name="clock" className="w-3 h-3" />
                {formatDuration(c.durationSeconds)}
              </span>
            ) : null}
            {c.lessonsCount ? (
              <span className="inline-flex items-center gap-1 px-2 h-[22px] rounded-full
                               bg-white/15 backdrop-blur-md ring-1 ring-white/10
                               font-bold">
                <Icon name="play" className="w-3 h-3" />
                {c.lessonsCount.toLocaleString('fa-IR')} درس
              </span>
            ) : null}
          </div>

          {/* Tiny enrollments stat — appears on hover */}
          {typeof c.enrollmentsCount === 'number' && c.enrollmentsCount > 0 && (
            <p className="mt-2 text-[10.5px] opacity-80 font-bold
                          opacity-0 group-hover:opacity-90 transition-opacity duration-300">
              {c.enrollmentsCount.toLocaleString('fa-IR')} نفر در حال یادگیری
            </p>
          )}
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
                 shadow-[0_4px_12px_-4px_rgba(13,128,116,.45)]
                 backdrop-blur-md"
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
                 shadow-[0_4px_12px_-4px_rgba(240,148,26,.55)]
                 backdrop-blur-md"
      style={{ backgroundColor: '#FFB033' }}
    >
      <Icon name="sparkles" className="w-3 h-3" />
      ویژه
    </span>
  );
}
