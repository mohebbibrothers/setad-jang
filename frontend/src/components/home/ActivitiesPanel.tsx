'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';

type Activity = {
  href: string;
  label: string;
  icon: string;        // path under /brand/
  iconAlt: string;
};

/**
 * Five fixed activities — order taken directly from the designer's mockup.
 * Each maps to a real backend app under /api/v1/*.
 */
const ACTIVITIES: Activity[] = [
  { href: '/tabyin',        label: 'جهاد تبیین',         icon: '/brand/icon-tabyin.png',   iconAlt: 'جهاد تبیین' },
  { href: '/kindness-wall', label: 'دیوار مهربانی',      icon: '/brand/icon-kindness.png', iconAlt: 'دیوار مهربانی' },
  { href: '/lms',           label: 'قرارگاه آموزشی',     icon: '/brand/icon-lms.png',      iconAlt: 'قرارگاه آموزشی' },
  { href: '/r4j',           label: 'جایزه برای عدالت',   icon: '/brand/icon-r4j.png',      iconAlt: 'جایزه برای عدالت' },
  { href: '/madadkar',      label: 'پشتیبانی مالی جنگ',  icon: '/brand/icon-warfund.png',  iconAlt: 'پشتیبانی مالی جنگ' },
];

/**
 * Curved teal panel with 5 white pill cards, exactly matching the
 * designer's mockup:
 *   - The panel uses the original asset (Asset 1) as its background image,
 *     so the wave-pattern and chevron notch render pixel-faithfully.
 *   - The 5 cards overflow the bottom edge of the panel (the bottom half
 *     of every card sits *outside* the teal area on the white page bg).
 *   - 5 fixed cards always, never dynamic.
 */
export function ActivitiesPanel() {
  return (
    <section
      className="relative -mt-4 md:-mt-8 z-[5] pt-8 pb-24 md:pt-12 md:pb-32"
      aria-labelledby="activities-title"
    >
      <div className="container-edge">
        <div className="relative">
          {/* Decorative panel — graphic comes from designer asset for pixel fidelity */}
          <div
            className="relative rounded-[2rem] md:rounded-[2.5rem] overflow-hidden text-white
                       min-h-[280px] md:min-h-[320px] flex items-start justify-center
                       pt-14 md:pt-16 px-5 md:px-12"
            style={{
              backgroundImage: 'url(/brand/activities-panel.png)',
              backgroundSize: '100% 100%',
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'center top',
            }}
          >
            <motion.h2
              id="activities-title"
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="text-xl md:text-2xl font-extrabold text-center drop-shadow-sm"
            >
              اهم فعالیت‌ها
            </motion.h2>
          </div>

          {/* 5 cards overflow the bottom of the panel */}
          <div className="absolute inset-x-4 md:inset-x-12 -bottom-12 md:-bottom-16 z-10
                          grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 md:gap-4 lg:gap-6">
            {ACTIVITIES.map((a, i) => (
              <motion.div
                key={a.href}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.07 }}
              >
                <Link
                  href={a.href}
                  className="group flex flex-col items-center text-center
                             rounded-2xl md:rounded-3xl bg-white text-ink-700
                             p-4 md:p-5 lg:p-6
                             shadow-[0_12px_28px_-10px_rgba(0,0,0,0.18)]
                             hover:-translate-y-1.5 hover:shadow-[0_20px_40px_-10px_rgba(0,0,0,0.25)]
                             transition-all duration-300 h-full border border-black/[0.03]"
                >
                  <div className="w-14 h-14 md:w-[62px] md:h-[62px] flex items-center justify-center
                                  transition-transform duration-300 group-hover:scale-110">
                    <Image
                      src={a.icon}
                      alt={a.iconAlt}
                      width={62}
                      height={62}
                      className="w-full h-full object-contain"
                    />
                  </div>
                  <p className="mt-3 md:mt-4 text-[12.5px] md:text-[14px] font-semibold leading-tight">
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
