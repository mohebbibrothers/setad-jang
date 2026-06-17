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
 * Activities panel — designer-faithful (v14b).
 *
 *  - Green wave panel (Asset 1 PNG bg) with generous top + bottom padding
 *    so the title sits centred and there is room for cards to overlap
 *    the bottom edge.
 *  - SOFT TOP FADE inside the panel: white→transparent linear-gradient
 *    overlay that lets the hero photo above bleed gently through the
 *    upper edge. The fade is masked off in the center 12% so the
 *    chevron-down notch stays sharp.
 *  - White pill CARDS are siblings of the panel, pulled UP with negative
 *    top margin so their top half sits inside the panel and their bottom
 *    half overflows below it. Thin brand-400 border around each card
 *    (per the green hairline in the mockup).
 *  - Fully responsive: 2 / 3 / 5 columns; icon and label sizes step up
 *    across breakpoints.
 */
export function ActivitiesPanel() {
  return (
    <section
      className="relative mt-8 md:mt-10 pb-20 md:pb-24"
      aria-labelledby="activities-title"
    >
      <div className="container-edge">
        <div className="relative">
          {/* Green wave panel — shorter than before so the cards
              overlap the bottom edge by ~half (matches mockup). */}
          <div
            className="relative text-white px-4 sm:px-8 md:px-12
                       pt-10 sm:pt-12 md:pt-[3.25rem] lg:pt-14
                       pb-12 sm:pb-14 md:pb-16 lg:pb-[4.5rem]
                       min-h-[160px] sm:min-h-[190px] md:min-h-[220px] lg:min-h-[240px]"
            style={{
              backgroundImage: 'url(/brand/activities-panel.png)',
              backgroundSize: '100% 100%',
              backgroundRepeat: 'no-repeat',
            }}
          >
            {/* Soft top-edge fade — hero photo bleeds gently through.
                Masked in the center 12% so the chevron notch stays sharp. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-0 h-[55px]"
              style={{
                background:
                  'linear-gradient(to bottom, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0.15) 60%, rgba(255,255,255,0) 100%)',
                WebkitMaskImage:
                  'linear-gradient(to right, #000 0%, #000 44%, transparent 44%, transparent 56%, #000 56%, #000 100%)',
                maskImage:
                  'linear-gradient(to right, #000 0%, #000 44%, transparent 44%, transparent 56%, #000 56%, #000 100%)',
              }}
            />

            <motion.h2
              id="activities-title"
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="relative text-center text-xl md:text-[26px] font-extrabold text-white
                         drop-shadow-[0_2px_8px_rgba(0,0,0,0.20)]"
            >
              اهم فعالیت‌ها
            </motion.h2>
          </div>

          {/* CARDS — perfect-square pills with a thicker brand border.
              Pulled up with negative margin so they overlap the panel's
              bottom edge by ~50%. Fully responsive with tuned scaling
              at extra breakpoints (380 / 560) for cleaner small-viewport
              fits. */}
          <div
            className="relative grid grid-cols-2 min-[560px]:grid-cols-3 md:grid-cols-5
                       gap-2.5 min-[380px]:gap-3 min-[560px]:gap-3.5 md:gap-4 lg:gap-[1.125rem] xl:gap-5
                       -mt-9 min-[560px]:-mt-11 md:-mt-12 lg:-mt-[3.25rem]
                       px-1 min-[380px]:px-2 md:px-4 lg:px-6"
          >
            {ACTIVITIES.map((a, i) => (
              <motion.div
                key={a.href}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
              >
                <Link
                  href={a.href}
                  className="group flex flex-col items-center justify-between
                             aspect-square w-full
                             bg-white text-ink-700
                             border-[2.5px] min-[560px]:border-[3px] lg:border-[3.5px]
                             border-brand-400 hover:border-brand-500
                             rounded-[1.125rem] md:rounded-[1.25rem] lg:rounded-[1.5rem]
                             p-3.5 min-[380px]:p-4 min-[560px]:p-4 md:p-[1.125rem] lg:p-5
                             pb-2.5 md:pb-3.5
                             shadow-[0_14px_28px_-16px_rgba(0,0,0,0.30)]
                             hover:-translate-y-1 hover:shadow-[0_22px_42px_-16px_rgba(0,0,0,0.35)]
                             transition-all duration-300"
                >
                  <div className="flex-1 flex items-center justify-center w-full max-h-[65%]">
                    <div
                      className="w-[42px] h-[42px] min-[380px]:w-[46px] min-[380px]:h-[46px]
                                 min-[560px]:w-[50px] min-[560px]:h-[50px]
                                 md:w-[54px] md:h-[54px]
                                 lg:w-[60px] lg:h-[60px]
                                 xl:w-[64px] xl:h-[64px]
                                 group-hover:scale-110 transition-transform"
                    >
                      <Image
                        src={a.icon}
                        alt={a.iconAlt}
                        width={64}
                        height={64}
                        className="w-full h-full object-contain"
                      />
                    </div>
                  </div>
                  <p
                    className="text-[10.5px] min-[380px]:text-[11.5px] min-[560px]:text-[12px]
                               md:text-[12.5px] lg:text-[13.5px] xl:text-[14.5px]
                               font-semibold text-ink-700 leading-[1.25] text-center mt-1.5
                               whitespace-nowrap md:whitespace-normal"
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
