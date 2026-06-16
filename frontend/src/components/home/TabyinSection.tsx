'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Heart, LinkIcon, Quote } from 'lucide-react';
import { SectionTitle } from './SectionTitle';

/**
 * Backend contract (apps/tabyin):
 *   GET /api/v1/tabyin/contents/?page=1
 * content: id, slug, title, summary, cover_image_url, content_type
 *  - cover/text/quote variations are supported in the design.
 */
export type TabyinItem = {
  id: string;
  slug: string;
  title?: string;        // optional when item is image-only
  summary?: string;      // for quote / text variant
  coverUrl?: string;
  variant?: 'cover' | 'quote';
  /** Optional masonry sizing hints */
  tall?: boolean;        // span 2 rows
  toneFrom?: string;
  toneTo?: string;
};

export function TabyinSection({ items }: { items: TabyinItem[] }) {
  return (
    <section className="section-y bg-white" id="tabyin">
      <div className="container-edge">
        <SectionTitle
          title="جهاد تبیین"
          description="بانک محتوای روشنگرانه، اینفوگرافیک‌ها و کلیپ‌های کوتاه برای روایت درست."
        />

        {/* Masonry-style grid using CSS grid auto-rows + row-span */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-4 auto-rows-[160px] md:auto-rows-[200px]">
          {items.map((it, i) => (
            <motion.article
              key={it.id}
              initial={{ opacity: 0, scale: 0.96 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ duration: 0.4, delay: i * 0.04 }}
              className={`relative rounded-2xl overflow-hidden bg-ink-100 group ${it.tall ? 'row-span-2' : 'row-span-1'}`}
            >
              {it.variant === 'quote' ? (
                <Link href={`/tabyin/${it.slug}`} className="block relative w-full h-full p-4 md:p-5
                  bg-brand-500 text-white flex items-center justify-center text-center">
                  <Quote className="absolute top-3 right-3 w-5 h-5 opacity-30" />
                  <p className="text-[12.5px] md:text-[13.5px] leading-7 font-medium">
                    {it.summary}
                  </p>
                </Link>
              ) : it.coverUrl ? (
                <Link href={`/tabyin/${it.slug}`} className="block relative w-full h-full">
                  <Image
                    src={it.coverUrl}
                    alt={it.title || 'محتوای تبیینی'}
                    fill
                    sizes="(max-width: 768px) 45vw, 22vw"
                    className="object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                  <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-90" />
                  {it.title && (
                    <p className="absolute bottom-3 inset-x-3 text-white text-[12.5px] font-bold leading-5 line-clamp-2 drop-shadow">
                      {it.title}
                    </p>
                  )}
                </Link>
              ) : (
                <Link
                  href={`/tabyin/${it.slug}`}
                  className="block w-full h-full"
                  style={{ background: `linear-gradient(135deg, ${it.toneFrom || '#0D8074'}, ${it.toneTo || '#053832'})` }}
                />
              )}

              {/* Bottom action row */}
              <div className="absolute bottom-2 left-2 flex items-center gap-1.5 z-10">
                <button
                  aria-label="کپی لینک"
                  className="w-7 h-7 rounded-full bg-white/85 hover:bg-white text-ink-700
                             flex items-center justify-center backdrop-blur transition-colors"
                >
                  <LinkIcon className="w-3.5 h-3.5" />
                </button>
                <button
                  aria-label="افزودن به علاقه‌مندی‌ها"
                  className="w-7 h-7 rounded-full bg-white/85 hover:bg-white text-ink-700
                             hover:text-rose-500 flex items-center justify-center backdrop-blur transition-colors"
                >
                  <Heart className="w-3.5 h-3.5" />
                </button>
              </div>
            </motion.article>
          ))}
        </div>

        {/* Load more CTA */}
        <div className="flex justify-center mt-8">
          <Link
            href="/tabyin"
            className="inline-flex items-center h-11 px-7 rounded-full bg-mint-500 hover:bg-mint-600
                       text-white text-[13.5px] font-bold shadow-soft transition-colors"
          >
            بارگذاری بیشتر
          </Link>
        </div>
      </div>
    </section>
  );
}
