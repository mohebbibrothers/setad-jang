'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';

type Activity = { href: string; label: string; icon: string; iconAlt: string };

const ACTIVITIES: Activity[] = [
  { href: '/tabyin',        label: 'جهاد تبیین',         icon: '/brand/icon-tabyin.png',   iconAlt: 'جهاد تبیین' },
  { href: '/kindness-wall', label: 'دیوار مهربانی',      icon: '/brand/icon-kindness.png', iconAlt: 'دیوار مهربانی' },
  { href: '/lms',           label: 'قرارگاه آموزشی',     icon: '/brand/icon-lms.png',      iconAlt: 'قرارگاه آموزشی' },
  { href: '/r4j',           label: 'جایزه برای عدالت',   icon: '/brand/icon-r4j.png',      iconAlt: 'جایزه برای عدالت' },
  { href: '/madadkar',      label: 'پشتیبانی مالی جنگ',  icon: '/brand/icon-warfund.png',  iconAlt: 'پشتیبانی مالی جنگ' },
];

/**
 * Activities panel — designer-faithful (v16).
 *
 * Highlights of this revision:
 *  - PANEL is shorter and uses fluid clamp() padding so it never feels
 *    too tall or too cramped at any viewport.
 *  - TITLE "اهم فعالیت‌ها" is pushed lower so it doesn't kiss the top
 *    wave edge of the asset.
 *  - SOFT TOP FADE inside the panel lets the hero photo above bleed
 *    gently through (masked off near the chevron notch).
 *  - CARDS overflow the panel's bottom edge ~50%. Each card has a
 *    BRAND-500 border (matches the panel teal exactly), perfect-square
 *    aspect ratio, icon constrained to 55% of card width with a hard
 *    max-width so it can NEVER spill out, and overflow-hidden so any
 *    edge case is clipped cleanly.
 *  - GRID uses minmax(0, 1fr) so columns truly share width equally and
 *    children with intrinsic sizes can't blow out the row.
 *  - LAYOUT scales smoothly with clamp() — fewer hard breakpoints means
 *    no more "jumpy" behaviour at intermediate widths.
 */
export function ActivitiesPanel() {
  return (
    <section
      className="relative mt-[4.5rem] md:mt-[5.5rem] lg:mt-[6.5rem] pb-20 md:pb-24"
      aria-labelledby="activities-title"
    >
      {/* Hero photo "ground reflection" — a vertically flipped, blurred,
          low-opacity copy of the defenders photo placed in the gap
          between the search bar and the green panel. Reads like the
          photo's reflection on a glossy floor (matches mockup). */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute z-[2] left-1/2
                   -top-[90px] h-[110px] w-[min(680px,90%)]
                   md:-top-[120px] md:h-[150px] md:w-[min(680px,75%)]
                   lg:-top-[150px] lg:h-[190px] lg:w-[min(680px,60%)]"
        style={{
          transform: 'translateX(-50%) scaleY(-1)',
          backgroundImage: 'url(/brand/hero-defenders.png)',
          backgroundSize: '100% auto',
          backgroundPosition: 'center top',
          backgroundRepeat: 'no-repeat',
          opacity: 0.28,
          filter: 'blur(12px) saturate(0.85)',
          WebkitMaskImage:
            'linear-gradient(to bottom, #000 0%, rgba(0,0,0,0.6) 40%, rgba(0,0,0,0.15) 75%, transparent 100%)',
          maskImage:
            'linear-gradient(to bottom, #000 0%, rgba(0,0,0,0.6) 40%, rgba(0,0,0,0.15) 75%, transparent 100%)',
        }}
      />

      <div className="container-edge">
        <div className="relative">
          {/* Green wave panel (fluid sizing) */}
          <div
            className="relative text-white"
            style={{
              backgroundImage: 'url(/brand/activities-panel.png)',
              backgroundSize: '100% 100%',
              backgroundRepeat: 'no-repeat',
              paddingTop: 'clamp(2rem, 5vw, 3rem)',
              paddingBottom: 'clamp(2.5rem, 5.5vw, 3.5rem)',
              paddingInline: 'clamp(1rem, 4vw, 3rem)',
              minHeight: 'clamp(140px, 18vw, 200px)',
            }}
          >
            <motion.h2
              id="activities-title"
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="relative text-center font-extrabold text-white
                         drop-shadow-[0_2px_8px_rgba(0,0,0,0.20)]"
              style={{
                marginTop: 'clamp(0.75rem, 2vw, 1.5rem)',
                fontSize: 'clamp(1.05rem, 2.4vw, 1.5rem)',
              }}
            >
              اهم فعالیت‌ها
            </motion.h2>
          </div>

          {/* CARDS — pulled up to overlap the panel bottom ~half. */}
          <div
            className="relative grid grid-cols-2 min-[480px]:grid-cols-3 min-[760px]:grid-cols-5"
            style={{
              gap: 'clamp(0.5rem, 1.4vw, 1.125rem)',
              marginTop: 'clamp(-2.5rem, -5vw, -1.75rem)',
              paddingInline: 'clamp(0.25rem, 1.5vw, 1.5rem)',
            }}
          >
            {ACTIVITIES.map((a, i) => (
              <motion.div
                key={a.href}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
                className="min-w-0"
              >
                <Link
                  href={a.href}
                  className="group flex flex-col items-center justify-between
                             aspect-square w-full min-w-0 max-w-full overflow-hidden
                             bg-white text-ink-700
                             border-brand-500 hover:border-brand-600
                             shadow-[0_14px_28px_-16px_rgba(0,0,0,0.30)]
                             hover:-translate-y-1 hover:shadow-[0_22px_42px_-16px_rgba(0,0,0,0.35)]
                             transition-all duration-300"
                  style={{
                    borderWidth: 'clamp(2px, 0.35vw, 3px)',
                    borderStyle: 'solid',
                    borderRadius: 'clamp(0.875rem, 1.6vw, 1.5rem)',
                    padding:
                      'clamp(0.625rem, 1.6vw, 1.125rem) clamp(0.375rem, 1vw, 0.875rem) clamp(0.5rem, 1.2vw, 1rem)',
                  }}
                >
                  <div
                    className="flex-shrink-0 flex items-center justify-center group-hover:scale-110 transition-transform"
                    style={{
                      width: '55%',
                      maxWidth: '64px',
                      aspectRatio: '1 / 1',
                      marginTop: 'auto',
                    }}
                  >
                    <Image
                      src={a.icon}
                      alt={a.iconAlt}
                      width={64}
                      height={64}
                      className="w-full h-full object-contain"
                    />
                  </div>
                  <p
                    className="font-semibold text-ink-700 text-center w-full
                               truncate min-[760px]:whitespace-normal min-[760px]:overflow-visible"
                    style={{
                      marginTop: 'auto',
                      fontSize: 'clamp(10px, 1.35vw, 14.5px)',
                      lineHeight: '1.25',
                      paddingTop: 'clamp(0.375rem, 1.2vw, 0.75rem)',
                    }}
                  >
                    {a.label}
                  </p>
                </Link>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
