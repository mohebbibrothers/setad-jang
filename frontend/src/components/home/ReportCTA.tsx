'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { Flag, ShieldCheck, Eye, Send } from 'lucide-react';

export function ReportCTA() {
  return (
    <section className="section-y">
      <div className="container-edge">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 to-brand-900 text-white p-8 md:p-12 lg:p-16">
          <div aria-hidden className="absolute inset-0 bg-grid-pattern opacity-10" />
          <div aria-hidden className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-accent-500/30 blur-3xl" />
          <div aria-hidden className="absolute -bottom-24 -right-24 w-96 h-96 rounded-full bg-brand-300/20 blur-3xl" />

          <div className="relative grid lg:grid-cols-2 gap-10 items-center">
            <div>
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/15 backdrop-blur text-sm font-semibold">
                <Flag className="w-4 h-4 text-accent-300" /> سامانه گزارش‌های مردمی
              </span>
              <h2 className="mt-5 text-3xl md:text-4xl lg:text-5xl font-extrabold leading-tight">
                صدای شما، گزارش شماست.
                <br />
                ثبت گزارش، آغاز پیگیری است.
              </h2>
              <p className="mt-5 text-white/85 leading-8 max-w-xl">
                با حفظ کامل حریم خصوصی، گزارش‌های خود را ثبت کنید و با کد رهگیری
                وضعیت بررسی را پیگیری نمایید.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link href="/public-reports/new" className="btn-accent btn-lg">
                  <Send className="w-5 h-5 -rotate-45" /> ثبت گزارش جدید
                </Link>
                <Link href="/public-reports/track" className="btn btn-lg bg-white/10 hover:bg-white/20 text-white border border-white/20">
                  <Eye className="w-5 h-5" /> پیگیری با کد رهگیری
                </Link>
              </div>
            </div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              className="lg:justify-self-end w-full max-w-md"
            >
              <div className="rounded-2xl bg-white/10 border border-white/15 backdrop-blur-md p-6 space-y-4">
                {[
                  { icon: ShieldCheck, t: 'حریم خصوصی محفوظ', d: 'اطلاعات شخصی شما عمومی نمی‌شود.' },
                  { icon: Eye,         t: 'پیگیری شفاف',      d: 'با کد رهگیری، هر مرحله را ببینید.' },
                  { icon: Flag,        t: 'بررسی توسط ادمین', d: 'تیم بررسی، گزارش‌ها را تأیید/رد می‌کند.' },
                ].map((row) => (
                  <div key={row.t} className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-xl bg-accent-500/95 text-ink-900 flex items-center justify-center shrink-0">
                      <row.icon className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="font-bold">{row.t}</p>
                      <p className="text-sm text-white/75 mt-0.5">{row.d}</p>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}
