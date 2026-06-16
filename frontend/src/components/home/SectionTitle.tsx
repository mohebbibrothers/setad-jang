'use client';

import { motion } from 'framer-motion';
import Image from 'next/image';
import { cn } from '@/lib/utils';

type Props = {
  title: string;
  description?: string;
  className?: string;
};

/**
 * Reusable section title block:
 * brand-coloured title centered with a small "+" sparkle pattern next to it,
 * followed by a max-w-prose description.
 * Matches the recurring section header style in the designer's mockup.
 */
export function SectionTitle({ title, description, className }: Props) {
  return (
    <div className={cn('text-center max-w-3xl mx-auto mb-8 md:mb-10', className)}>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.45 }}
        className="inline-flex items-center justify-center gap-3"
      >
        <h2 className="text-xl md:text-[26px] font-extrabold text-brand-600">{title}</h2>
        <Image
          src="/brand/pattern-plus.png"
          alt=""
          width={79}
          height={80}
          aria-hidden="true"
          className="w-12 h-12 md:w-14 md:h-14 object-contain opacity-90"
        />
      </motion.div>
      {description && (
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.45, delay: 0.1 }}
          className="mt-4 md:mt-5 text-ink-600 text-[14.5px] md:text-[15px] leading-8 max-w-2xl mx-auto"
        >
          {description}
        </motion.p>
      )}
    </div>
  );
}
