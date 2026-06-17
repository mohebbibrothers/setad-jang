'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';

type Activity = {
  href: string;
  label: string;
  icon: string;          // path under /brand/
  iconAlt: string;
};

/**
 * Static list — these are the 5 main pillars rendered exactly per the
 * designer's mockup. Order, icons, and labels are fixed by design.
 */
const ACTIVITIES: Activity[] = [
  { href: '/tabyin',        label: 'جهاد تبیین',         icon: '/brand/icon-tabyin.png',   iconAlt: 'جهاد تبیین' },
  { href: '/kindness-wall', label: 'دیوار مهربانی',      icon: '/brand/icon-kindness.png', iconAlt: 'دیوار مهربانی' },
  { href: '/lms',           label: 'قرارگاه آموزشی',     icon: '/brand/icon-lms.png',      iconAlt: 'قرارگاه آموزشی' },
  { href: '/r4j',           label: 'جایزه برای عدالت',   icon: '/brand/icon-r4j.png',      iconAlt: 'جایزه برای عدالت' },
  { href: '/madadkar',      label: 'پشتیبانی مالی جنگ',  icon: '/brand/icon-warfund.png',  iconAlt: 'پشتیبانی مالی جنگ' },
];

/**
 * Activities panel — uses the designer's official ribbon-shaped teal
 * banner (Asset 1) as the background, so the wavy edges and chevron-up
 * notch render exactly as the mockup intended.
 *
 * Overlapped slightly into the hero via negative margin for a single
 * continuous canvas (matches mockup).
 */
export function ActivitiesPanel() {
  return (
    <section
      className="relative pt-0 pb-20 md:pb-24 mt-2 md:mt-4 z-10"
      aria-labelledby="activities-title"
    >
      <div className="container-edge">
        <div
          className="relative text-white px-5 sm:px-8 md:px-12 pt-12 md:pt-14"
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
            className="text-center text-xl md:text-[26px] font-extrabold mb-7 md:mb-9 text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.2)]"
          >
            اهم فعالیت‌ها
          </motion.h2>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 md:gap-4 lg:gap-5">
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
                  className="group block rounded-2xl bg-white text-ink-700 p-4 md:p-5
                             shadow-[0_10px_28px_-14px_rgba(0,0,0,0.35)]
                             hover:-translate-y-1.5 hover:shadow-[0_18px_40px_-14px_rgba(0,0,0,0.4)]
                             transition-all duration-300 h-full flex flex-col items-center text-center"
                >
                  <div className="w-14 h-14 md:w-[60px] md:h-[60px] flex items-center justify-center
                                  group-hover:scale-110 transition-transform">
                    <Image
                      src={a.icon}
                      alt={a.iconAlt}
                      width={60}
                      height={60}
                      className="w-full h-full object-contain"
                    />
                  </div>
                  <p className="mt-3 md:mt-4 text-[13px] md:text-[14px] font-semibold text-ink-700 leading-tight">
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
