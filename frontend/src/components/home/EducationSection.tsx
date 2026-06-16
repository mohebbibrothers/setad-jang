'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';

/**
 * Backend contract (apps/lms):
 *   GET /api/v1/lms/categories/                → LMSCategory[]
 *   GET /api/v1/lms/courses/?category={slug}   → CourseSummary[]
 *
 * Course fields used (from CourseSummarySerializer):
 *   id, slug, title, subtitle, instructor_name, level, cover_image,
 *   lessons_count, estimated_duration_seconds, enrollments_count,
 *   graduates_count, is_featured, category{title, slug}
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
  level?: 'beginner' | 'intermediate' | 'advanced' | string;
  coverUrl?: string;
  lessonsCount?: number;
  durationSeconds?: number;
  enrollmentsCount?: number;
  isNew?: boolean;
  isFeatured?: boolean;
  categorySlug?: string;
  /** Fallback gradient when no cover */
  toneFrom?: string;
  toneTo?: string;
};

const ALL = { slug: 'all', title: 'همه آموزش‌ها' } as const;

const LEVEL_LABEL: Record<string, string> = {
  beginner: 'مقدماتی',
  intermediate: 'متوسط',
  advanced: 'پیشرفته',
};

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0 && m > 0) return `${h.toLocaleString('fa-IR')} ساعت و ${m.toLocaleString('fa-IR')} دقیقه`;
  if (h > 0) return `${h.toLocaleString('fa-IR')} ساعت`;
  return `${m.toLocaleString('fa-IR')} دقیقه`;
}

export function EducationSection({
  categories,
  courses,
}: {
  categories: EduCategory[];
  courses: CourseCard[];
}) {
  const [active, setActive] = useState<string>('all');

  // Always show "all" first; counts annotated dynamically
  const tabs = useMemo(() => {
    const cats = [ALL as EduCategory, ...categories];
    return cats.map((c) => ({
      ...c,
      count:
        c.slug === 'all'
          ? courses.length
          : courses.filter((x) => x.categorySlug === c.slug).length,
    }));
  }, [categories, courses]);

  const visibleCourses = useMemo(
    () => courses.filter((c) => active === 'all' || c.categorySlug === active).slice(0, 8),
    [courses, active],
  );

  /* ── Tab strip — horizontal scroll on mobile, scroll-arrows on desktop ── */
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [canPrev, setCanPrev] = useState(false);
  const [canNext, setCanNext] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => {
      // RTL: scrollLeft is <= 0 in many browsers; normalize
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

  function scrollBy(dx: number) {
    scrollRef.current?.scrollBy({ left: dx, behavior: 'smooth' });
  }

  return (
    <section className="section-y bg-white" id="education">
      <div className="container-edge">
        <SectionTitle
          title="قرارگاه آموزشی"
          description="دوره‌های جهادی، تخصصی و فرهنگی؛ هر دوره با کوییز پایان دوره، گواهی استعلام‌پذیر عمومی و رتبه‌بندی دانش‌پذیران."
        />

        {/* Tab strip wrapper with scroll arrows (desktop) */}
        <div className="relative mb-8">
          {/* Left arrow (towards "next" in LTR scroll dir; in RTL we mirror by sign) */}
          {canPrev && (
            <button
              type="button"
              aria-label="دسته‌های قبلی"
              onClick={() => scrollBy(200)}
              className="hidden md:inline-flex absolute right-0 top-1/2 -translate-y-1/2 z-10
                         w-9 h-9 rounded-full bg-white border border-ink-200 text-ink-600
                         items-center justify-center shadow-soft hover:border-brand-300 hover:text-brand-600
                         transition-colors"
            >
              <Icon name="chevron-right" className="w-4 h-4" />
            </button>
          )}
          {canNext && (
            <button
              type="button"
              aria-label="دسته‌های بعدی"
              onClick={() => scrollBy(-200)}
              className="hidden md:inline-flex absolute left-0 top-1/2 -translate-y-1/2 z-10
                         w-9 h-9 rounded-full bg-white border border-ink-200 text-ink-600
                         items-center justify-center shadow-soft hover:border-brand-300 hover:text-brand-600
                         transition-colors"
            >
              <Icon name="chevron-left" className="w-4 h-4" />
            </button>
          )}

          {/* Fade masks */}
          {canPrev && <div aria-hidden className="hidden md:block pointer-events-none absolute inset-y-0 right-9 w-10 bg-gradient-to-l from-white to-transparent z-[5]" />}
          {canNext && <div aria-hidden className="hidden md:block pointer-events-none absolute inset-y-0 left-9 w-10 bg-gradient-to-r from-white to-transparent z-[5]" />}

          <div
            ref={scrollRef}
            role="tablist"
            aria-label="دسته‌بندی دوره‌ها"
            className="flex items-center gap-1 border-b border-ink-100 overflow-x-auto no-scrollbar
                       md:px-12 scroll-smooth"
          >
            {tabs.map((c) => {
              const isActive = active === c.slug;
              return (
                <button
                  key={c.slug}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActive(c.slug)}
                  className={`relative inline-flex items-center gap-2 px-4 md:px-5 py-3 text-[13.5px] md:text-[14.5px]
                              font-semibold whitespace-nowrap transition-colors shrink-0 ${
                                isActive ? 'text-brand-600' : 'text-ink-500 hover:text-ink-800'
                              }`}
                >
                  <span>{c.title}</span>
                  {typeof c.count === 'number' && c.count > 0 && (
                    <span className={`inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5
                                      rounded-full text-[11px] font-bold tabular-nums ${
                                        isActive ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-500'
                                      }`}>
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

        {/* Course grid */}
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
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

        {/* Footer CTA */}
        <div className="flex justify-center mt-10">
          <Link
            href="/lms"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-bold text-[14px]
                       shadow-soft transition-colors"
          >
            مشاهده کتابخانه کامل آموزش‌ها
            <Icon name="arrow-left" className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */

function CourseTile({ c, delay = 0 }: { c: CourseCard; delay?: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.4, delay }}
      className="group"
    >
      <Link
        href={`/lms/courses/${c.slug}`}
        className="relative block aspect-[4/5] rounded-2xl overflow-hidden bg-ink-200
                   shadow-soft hover:shadow-card hover:-translate-y-1 transition-all duration-300"
      >
        {c.coverUrl ? (
          <Image
            src={c.coverUrl}
            alt={c.title}
            fill
            sizes="(max-width: 768px) 45vw, (max-width: 1024px) 30vw, 22vw"
            className="object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{
              background: `linear-gradient(135deg, ${c.toneFrom || '#0D8074'}, ${c.toneTo || '#053832'})`,
            }}
          >
            <Icon name="play" className="w-20 h-20 text-white/60" />
          </div>
        )}

        {/* Bottom gradient + text */}
        <div aria-hidden className="absolute inset-x-0 bottom-0 h-2/3
                                    bg-gradient-to-t from-black/75 via-black/30 to-transparent" />

        {/* Badges row */}
        <div className="absolute top-3 right-3 left-3 flex items-start justify-between gap-2">
          {c.isNew && (
            <span className="inline-flex items-center px-2.5 h-7 rounded-full
                             bg-mint-500 text-white text-[11px] font-bold shadow-soft">
              جدید
            </span>
          )}
          {c.isFeatured && (
            <span className="inline-flex items-center gap-1 px-2.5 h-7 rounded-full
                             bg-gold-500 text-ink-900 text-[11px] font-bold shadow-soft mr-auto">
              <Icon name="sparkles" className="w-3 h-3" />
              ویژه
            </span>
          )}
        </div>

        {/* Title block */}
        <div className="absolute inset-x-0 bottom-0 p-4 text-white">
          {c.instructor && (
            <p className="text-[11px] opacity-90 mb-1 line-clamp-1">{c.instructor}</p>
          )}
          <h3 className="text-[14px] md:text-[15px] font-bold leading-6 line-clamp-2 drop-shadow">
            {c.title}
          </h3>

          {/* Meta row */}
          <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] opacity-90">
            {c.lessonsCount ? (
              <span className="inline-flex items-center gap-1">
                <Icon name="play" className="w-3 h-3" />
                {c.lessonsCount.toLocaleString('fa-IR')} درس
              </span>
            ) : null}
            {c.durationSeconds ? (
              <span className="inline-flex items-center gap-1">
                <Icon name="clock" className="w-3 h-3" />
                {formatDuration(c.durationSeconds)}
              </span>
            ) : null}
            {c.level && (
              <span className="inline-flex items-center gap-1">
                <Icon name="graduation" className="w-3 h-3" />
                {LEVEL_LABEL[c.level] || c.level}
              </span>
            )}
          </div>
        </div>
      </Link>
    </motion.article>
  );
}
