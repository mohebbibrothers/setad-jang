'use client';

import { useState } from 'react';
import Script from 'next/script';
import { Plus, Minus } from 'lucide-react';

const FAQS = [
  {
    q: 'بعثت مردم چیست و چه هدفی دارد؟',
    a: 'بعثت مردم یک پلتفرم یکپارچه مردمی برای جهاد تبیین، مددکاری، آموزش، گزارش‌های مردمی و دیوار مهربانی است؛ هدف، فعال‌سازی ظرفیت‌های مردمی برای حل مسائل اجتماعی و فرهنگی است.',
  },
  {
    q: 'مشارکت من در کمپین‌های مددکاری چگونه پیگیری می‌شود؟',
    a: 'هر مشارکت دارای کد رهگیری و سند مالی است و در پنل کاربری شما، وضعیت کمپین، گزارش هزینه‌کرد و رسید پرداخت قابل مشاهده است.',
  },
  {
    q: 'آیا اطلاعات گزارش‌های مردمی، عمومی می‌شود؟',
    a: 'خیر. حریم خصوصی شما کاملاً محفوظ است. اطلاعات هویتی شما عمومی نخواهد شد و صرفاً برای پیگیری توسط تیم بررسی استفاده می‌شود.',
  },
  {
    q: 'گواهی دوره‌های آموزشی، رسمی و قابل استعلام است؟',
    a: 'بله. هر گواهی دارای کد یکتای استعلام عمومی است که از طریق صفحه «استعلام گواهی» قابل راستی‌آزمایی است.',
  },
  {
    q: 'برای ثبت آگهی در دیوار مهربانی باید چه شرایطی داشته باشم؟',
    a: 'تکمیل پروفایل و تأیید شماره موبایل کافی است. آگهی پس از بررسی سریع تیم نظارت، عمومی می‌شود.',
  },
];

export function FAQ() {
  const [open, setOpen] = useState<number | null>(0);

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: FAQS.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  };

  return (
    <section className="section-y bg-white">
      <div className="container-edge max-w-4xl">
        <div className="text-center mb-10">
          <span className="eyebrow">سؤالات متداول</span>
          <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
            هرچه باید درباره بعثت مردم بدانید
          </h2>
        </div>

        <div className="space-y-3">
          {FAQS.map((f, i) => {
            const isOpen = open === i;
            return (
              <div
                key={f.q}
                className={`rounded-2xl border transition-colors
                            ${isOpen ? 'bg-brand-50/40 border-brand-200' : 'bg-white border-ink-100 hover:border-brand-200'}`}
              >
                <button
                  type="button"
                  className="w-full flex items-center gap-4 p-5 text-right"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : i)}
                >
                  <span className="flex-1 font-bold text-ink-900 text-[15.5px]">{f.q}</span>
                  <span
                    className={`w-9 h-9 shrink-0 rounded-full flex items-center justify-center
                                ${isOpen ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-700'}`}
                  >
                    {isOpen ? <Minus className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                  </span>
                </button>
                <div
                  className={`grid transition-[grid-template-rows] duration-300 ease-out
                              ${isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
                >
                  <div className="overflow-hidden">
                    <p className="px-5 pb-5 text-ink-600 leading-8 text-[14.5px]">{f.a}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <Script
          id="ld-json-faq"
          type="application/ld+json"
          strategy="afterInteractive"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </div>
    </section>
  );
}
