'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  User, Fingerprint, Phone, Users as Family,
  Settings, MessageSquareText, Paperclip, Send,
} from 'lucide-react';
import { SectionTitle } from './SectionTitle';

/**
 * Backend contract (apps/public_reports):
 *   GET  /api/v1/public-reports/subjects/
 *   POST /api/v1/public-reports/reports/
 *
 * For homepage we render the form inline so users can submit without leaving.
 * Real submission will POST to backend; here we just demo state and link.
 */
type FormState = {
  first_name: string;
  last_name: string;
  national_id: string;
  phone: string;
  subject_id: string;
  description: string;
};

const INITIAL: FormState = {
  first_name: '', last_name: '', national_id: '', phone: '',
  subject_id: '', description: '',
};

export function PublicReportSection({
  subjects = [
    { id: '1', name: 'گزارش فساد اقتصادی' },
    { id: '2', name: 'گزارش تخلف اجتماعی' },
    { id: '3', name: 'گزارش امنیتی' },
    { id: '4', name: 'گزارش فرهنگی' },
    { id: '5', name: 'سایر موارد' },
  ],
}: { subjects?: { id: string; name: string }[] }) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [robot, setRobot] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  function update<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!robot) return;
    setSubmitting(true);
    // Real call (subject to envelope/CSRF when integrated)
    setTimeout(() => { setSubmitting(false); setSubmitted(true); setForm(INITIAL); }, 1200);
  }

  return (
    <section className="section-y" id="reports">
      <div className="container-edge">
        <SectionTitle
          title="گزارش‌های مردمی"
          description="چشم‌های شما، تیزترین چشم‌هاست. هر سرنخ، هر فساد و هر ناهنجاری را با ما در میان بگذارید — هویتتان محرمانه می‌ماند و هر گزارش با کد رهگیری قابل پیگیری است."
        />

        <motion.form
          onSubmit={onSubmit}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="bg-brand-500 rounded-[2rem] md:rounded-[2.5rem] p-5 md:p-8 lg:p-10 text-white relative overflow-hidden"
        >
          {/* Decorative subtle pattern */}
          <div aria-hidden="true" className="absolute inset-0 opacity-[0.06] pointer-events-none"
            style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.7) 1px, transparent 1px)', backgroundSize: '22px 22px' }} />

          <div className="relative grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
            <Field icon={<User className="w-4 h-4" />} placeholder="نام" value={form.first_name}
                   onChange={(v) => update('first_name', v)} />
            <Field icon={<Family className="w-4 h-4" />} placeholder="نام خانوادگی" value={form.last_name}
                   onChange={(v) => update('last_name', v)} />
            <Field icon={<Fingerprint className="w-4 h-4" />} placeholder="کد ملی" value={form.national_id}
                   onChange={(v) => update('national_id', v)} inputMode="numeric" />
            <Field icon={<Phone className="w-4 h-4" />} placeholder="شماره تماس" value={form.phone}
                   onChange={(v) => update('phone', v)} type="tel" inputMode="tel" />

            <div className="md:col-span-2 relative">
              <Settings className="w-4 h-4 text-brand-500 absolute right-4 top-1/2 -translate-y-1/2 z-10" />
              <select
                value={form.subject_id}
                onChange={(e) => update('subject_id', e.target.value)}
                aria-label="دسته‌بندی"
                className="w-full h-12 pr-10 pl-4 rounded-xl bg-white text-ink-800 text-[14px]
                           outline-none focus:ring-2 focus:ring-white/60 appearance-none"
              >
                <option value="">دسته‌بندی را انتخاب کنید</option>
                {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>

            <div className="md:col-span-2 relative">
              {/* Icon aligned to first text line baseline (top:1.25rem matches padding-top + half line-height) */}
              <MessageSquareText className="w-4 h-4 text-brand-500 absolute right-4 top-[1.25rem] z-10 pointer-events-none" />
              <textarea
                value={form.description}
                onChange={(e) => update('description', e.target.value)}
                placeholder="شرح گزارش یا سرنخ شما…"
                aria-label="شرح گزارش"
                rows={5}
                dir="rtl"
                className="w-full pr-10 pl-4 pt-[1.15rem] pb-4 rounded-xl bg-white text-ink-800 text-[14px]
                           outline-none focus:ring-2 focus:ring-white/60 resize-y min-h-[140px]
                           text-right leading-7"
              />
            </div>
          </div>

          {/* Footer row */}
          <div className="relative mt-5 md:mt-6 flex flex-col md:flex-row gap-3 items-stretch md:items-center">
            <label className="inline-flex items-center justify-center gap-2 h-12 px-5 rounded-xl
                              bg-white/15 hover:bg-white/20 cursor-pointer text-sm font-semibold transition-colors">
              <Paperclip className="w-4 h-4" />
              پیوست فایل یا رسانه
              <input type="file" className="hidden" />
            </label>

            <label className="inline-flex items-center gap-2.5 h-12 px-5 rounded-xl
                              bg-white/95 hover:bg-white cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={robot}
                onChange={(e) => setRobot(e.target.checked)}
                className="sr-only peer"
              />
              <span className="w-5.5 h-5.5 rounded-md border-2 border-ink-300 bg-white
                               flex items-center justify-center transition-all
                               peer-checked:bg-brand-500 peer-checked:border-brand-500"
                    style={{ width: '22px', height: '22px' }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
                     strokeLinecap="round" strokeLinejoin="round"
                     className={`w-3.5 h-3.5 text-white transition-opacity ${robot ? 'opacity-100' : 'opacity-0'}`}>
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </span>
              <span className="text-ink-800 font-semibold text-sm">من ربات نیستم</span>
            </label>

            <button
              type="submit"
              disabled={!robot || submitting}
              className="md:mr-auto inline-flex items-center justify-center gap-2 h-12 px-8 rounded-xl
                         bg-brand-700 hover:bg-brand-900 text-white text-sm font-bold
                         disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-4 h-4 -rotate-45" />
              {submitting ? 'در حال ارسال…' : 'ارسال'}
            </button>
          </div>

          {submitted && (
            <p className="relative mt-4 text-white bg-white/15 rounded-xl px-4 py-3 text-sm">
              ✅ گزارش شما با موفقیت دریافت شد. به‌زودی نتیجه بررسی به شما اطلاع داده می‌شود.
            </p>
          )}
        </motion.form>
      </div>
    </section>
  );
}

function Field({
  icon, placeholder, value, onChange, type = 'text', inputMode,
}: {
  icon: React.ReactNode; placeholder: string; value: string; onChange: (v: string) => void;
  type?: string; inputMode?: 'numeric' | 'tel';
}) {
  return (
    <div className="relative">
      <span className="absolute right-4 top-1/2 -translate-y-1/2 text-brand-500 z-10 pointer-events-none">{icon}</span>
      <input
        type={type}
        inputMode={inputMode}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        dir="rtl"
        className="w-full h-12 pr-10 pl-4 rounded-xl bg-white text-ink-800 text-[14px]
                   outline-none focus:ring-2 focus:ring-white/60 placeholder:text-ink-400 text-right"
      />
    </div>
  );
}
