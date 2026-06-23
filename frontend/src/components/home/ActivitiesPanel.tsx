'use client';

import Image from 'next/image';
import { motion } from 'framer-motion';

/** Smooth-scroll handler for the in-page anchors.
 *  Next's <Link> only updates the URL hash; on a page that has been
 *  scroll-restored or where the hash doesn't change because the user is
 *  already on the route, the browser sometimes skips the scroll.
 *  This handler scrolls reliably to the target section using the native
 *  scrollIntoView() API + `behavior: 'smooth'`, accounts for the sticky
 *  header by reading the section's computed `scroll-margin-top`, and
 *  still updates the URL hash so links remain shareable. */
function scrollToAnchor(e: React.MouseEvent<HTMLAnchorElement>, href: string) {
  if (!href.startsWith('#')) return;
  const id = href.slice(1);
  const el = typeof document !== 'undefined' ? document.getElementById(id) : null;
  if (!el) return;
  e.preventDefault();
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  // Keep the URL shareable without an extra history entry.
  if (typeof window !== 'undefined') {
    window.history.replaceState(null, '', href);
  }
}

type Activity = { href: string; label: string; icon: string; iconAlt: string };

// Order matches the on-page section order so the right-most card (RTL
// "first") is the first section the user scrolls to. Each href is an
// in-page anchor so clicking smooth-scrolls to that section instead of
// navigating away.
const ACTIVITIES: Activity[] = [
  { href: '#warfund',  label: 'پشتیبانی مالی جنگ',  icon: '/brand/icon-warfund.png',  iconAlt: 'پشتیبانی مالی جنگ' },
  { href: '#justice',  label: 'جایزه برای عدالت',   icon: '/brand/icon-r4j.png',      iconAlt: 'جایزه برای عدالت' },
  { href: '#education', label: 'قرارگاه آموزشی',    icon: '/brand/icon-lms.png',      iconAlt: 'قرارگاه آموزشی' },
  { href: '#kindness', label: 'دیوار مهربانی',      icon: '/brand/icon-kindness.png', iconAlt: 'دیوار مهربانی' },
  { href: '#tabyin',   label: 'جهاد تبیین',         icon: '/brand/icon-tabyin.png',   iconAlt: 'جهاد تبیین' },
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
      className="relative mt-12 md:mt-16 lg:mt-20 pb-20 md:pb-24"
      aria-labelledby="activities-title"
    >
      {/* Soft ambient shadow ABOVE the green panel — a wide, low-opacity
          band that fades from brand-tinted bottom (where it touches the
          panel) to fully transparent at the top. Pure CSS gradient,
          no images. Clean, soft, designer-faithful.
          z-0: kept BELOW the hero's overlapping search dropdown (which
          floats at z-[80] within its own section). */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 z-0
                   -top-[60px] h-[80px]
                   md:-top-[80px] md:h-[110px]
                   lg:-top-[100px] lg:h-[140px]"
        style={{
          background:
            'radial-gradient(ellipse 80% 100% at 50% 100%, rgba(11,53,48,0.20) 0%, rgba(11,53,48,0.12) 30%, rgba(11,53,48,0.05) 60%, rgba(11,53,48,0) 100%)',
          filter: 'blur(14px)',
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

          {/* CARDS — pulled up to overlap the panel bottom ~half.
              Switched from CSS Grid to flex+wrap+justify-center so any
              orphan card in the last row auto-centres at narrow widths
              (mobile 2-col: 5th card sits dead-centre; tablet 3-col:
              4th and 5th flank the centre). Card width is computed to
              match the parent gap so columns stay perfectly aligned.    */}
          <div
            className="relative flex flex-wrap justify-center"
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
                className="min-w-0
                           w-[calc((100%-clamp(0.5rem,1.4vw,1.125rem))/2)]
                           min-[480px]:w-[calc((100%-2*clamp(0.5rem,1.4vw,1.125rem))/3)]
                           min-[760px]:w-[calc((100%-4*clamp(0.5rem,1.4vw,1.125rem))/5)]"
              >
                <a
                  href={a.href}
                  onClick={(e) => scrollToAnchor(e, a.href)}
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
                </a>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
