'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';

type Activity = {
  href: string;
  label: string;
  icon: string;
  iconAlt: string;
};

const ACTIVITIES: Activity[] = [
  { href: '/tabyin',        label: 'جهاد تبیین',         icon: '/brand/icon-tabyin.png',   iconAlt: 'جهاد تبیین' },
  { href: '/kindness-wall', label: 'دیوار مهربانی',      icon: '/brand/icon-kindness.png', iconAlt: 'دیوار مهربانی' },
  { href: '/lms',           label: 'قرارگاه آموزشی',     icon: '/brand/icon-lms.png',      iconAlt: 'قرارگاه آموزشی' },
  { href: '/r4j',           label: 'جایزه برای عدالت',   icon: '/brand/icon-r4j.png',      iconAlt: 'جایزه برای عدالت' },
  { href: '/madadkar',      label: 'پشتیبانی مالی جنگ',  icon: '/brand/icon-warfund.png',  iconAlt: 'پشتیبانی مالی جنگ' },
];

/**
 * Activities panel — pixel-faithful to designer mockup.
 *
 * Top-edge shadow: a single blurred ::before ellipse — soft enough that
 * the hero photo behind the panel stays faintly visible through it
 * (no harsh dark band).
 *
 * Cards: 4:4.6 aspect (slightly taller than wide). Icon is bottom-anchored
 * using mt-auto so it visually sits in the LOWER half of the card, with
 * a thin brand-200 outline around the card matching the green hairline
 * in the mockup. Fully responsive — 2/3/5 columns across breakpoints.
 */
export function ActivitiesPanel() {
  return (
    <section
      className="relative pt-8 md:pt-10 pb-16 md:pb-20"
      aria-labelledby="activities-title"
    >
      <div className="container-edge">
        {/* Wrapper that draws a SOFT top-edge shadow ABOVE the panel */}
        <div
          className="relative isolate
                     before:content-[''] before:absolute before:left-[3%] before:right-[3%]
                     before:-top-[22px] before:h-9 before:-z-10 before:pointer-events-none
                     before:rounded-full before:blur-[18px]
                     before:[background:radial-gradient(ellipse_100%_100%_at_center_bottom,rgba(11,53,48,0.18)_0%,rgba(11,53,48,0.09)_35%,rgba(11,53,48,0.04)_60%,rgba(11,53,48,0)_100%)]"
        >
          <div
            className="relative text-white px-4 sm:px-6 md:px-10 lg:px-12
                       pt-9 sm:pt-10 md:pt-12 lg:pt-[3.25rem]
                       pb-8 sm:pb-9 md:pb-10 lg:pb-11"
            style={{
              backgroundImage: 'url(/brand/activities-panel.png)',
              backgroundSize: '100% 100%',
              backgroundRepeat: 'no-repeat',
            }}
          >
            <motion.h2
              id="activities-title"
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="text-center font-extrabold text-white
                         text-[1.1rem] sm:text-[1.25rem] md:text-[1.45rem] lg:text-[1.6rem]
                         drop-shadow-[0_2px_8px_rgba(0,0,0,0.18)]"
            >
              اهم فعالیت‌ها
            </motion.h2>

            {/* 5 cards — responsive 2 / 3 / 5 columns */}
            <div className="mt-6 sm:mt-7 md:mt-8
                            grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5
                            gap-2.5 sm:gap-3 md:gap-3.5 lg:gap-[1.125rem]">
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
                    className="group flex flex-col items-center bg-white text-ink-700
                               border-[1.5px] border-brand-200 hover:border-brand-400
                               rounded-2xl md:rounded-[1.25rem]
                               px-2 sm:px-2.5 md:px-3
                               pt-3.5 sm:pt-4 md:pt-[1.125rem]
                               pb-3 sm:pb-3.5 md:pb-4
                               shadow-[0_8px_22px_-12px_rgba(0,0,0,0.22)]
                               hover:-translate-y-1 hover:shadow-[0_16px_32px_-14px_rgba(0,0,0,0.30)]
                               transition-all duration-300"
                    style={{ aspectRatio: '4 / 4.6' }}
                  >
                    {/* Icon — pushed to lower half via mt-auto */}
                    <div
                      className="mt-auto group-hover:scale-[1.08] transition-transform
                                 w-[38px] h-[38px] sm:w-11 sm:h-11 md:w-[50px] md:h-[50px] lg:w-14 lg:h-14"
                    >
                      <Image
                        src={a.icon}
                        alt={a.iconAlt}
                        width={56}
                        height={56}
                        className="w-full h-full object-contain"
                      />
                    </div>
                    {/* Label — sits below icon, centred */}
                    <p className="text-center mt-2.5 md:mt-3 leading-tight font-semibold text-ink-700
                                  text-[11px] sm:text-[12px] md:text-[13px] lg:text-[14px]">
                      {a.label}
                    </p>
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
