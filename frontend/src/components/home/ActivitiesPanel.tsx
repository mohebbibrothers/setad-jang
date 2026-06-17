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
      className="relative mt-10 md:mt-12 pb-24 md:pb-28"
      aria-labelledby="activities-title"
    >
      <div className="container-edge">
        <div className="relative">
          {/* Green wave panel */}
          <div
            className="relative text-white px-4 sm:px-8 md:px-12
                       pt-12 sm:pt-14 md:pt-16
                       pb-16 sm:pb-20 md:pb-24
                       min-h-[200px] md:min-h-[280px] lg:min-h-[320px]"
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

          {/* CARDS — pulled UP with negative margin so they overlap the
              panel's bottom edge by ~50%. Fully responsive. */}
          <div
            className="relative grid grid-cols-2 min-[480px]:grid-cols-3 md:grid-cols-5
                       gap-3 md:gap-4 lg:gap-5
                       -mt-10 md:-mt-14 lg:-mt-16
                       px-2 md:px-4 lg:px-6"
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
                             aspect-[1/1.05] w-full
                             bg-white text-ink-700
                             border-[1.5px] border-brand-400 hover:border-brand-500
                             rounded-2xl md:rounded-[1.5rem]
                             p-3 sm:p-4 md:p-5 pb-2.5 md:pb-3.5
                             shadow-[0_14px_28px_-16px_rgba(0,0,0,0.30)]
                             hover:-translate-y-1 hover:shadow-[0_22px_42px_-16px_rgba(0,0,0,0.35)]
                             transition-all duration-300"
                >
                  <div className="flex-1 flex items-center justify-center w-full">
                    <div
                      className="w-12 h-12 min-[480px]:w-[52px] min-[480px]:h-[52px]
                                 md:w-[60px] md:h-[60px] lg:w-[66px] lg:h-[66px]
                                 group-hover:scale-110 transition-transform"
                    >
                      <Image
                        src={a.icon}
                        alt={a.iconAlt}
                        width={66}
                        height={66}
                        className="w-full h-full object-contain"
                      />
                    </div>
                  </div>
                  <p
                    className="text-[11.5px] min-[480px]:text-[12.5px] md:text-[13.5px] lg:text-[14.5px]
                               font-semibold text-ink-700 leading-tight text-center mt-1.5
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
