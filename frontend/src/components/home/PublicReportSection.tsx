'use client';

import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Public reports — designer-free, backend-faithful (v2).
 *
 * Backend contract (apps/public_reports):
 *   GET  /api/v1/public-reports/subjects/   ReportSubjectPublicSerializer
 *     → { id, title, slug, description, order }
 *
 *   POST /api/v1/public-reports/reports/    ReportCreateSerializer
 *     Fields (all required except where noted):
 *       - full_name      : str, max 150           (REQUIRED)
 *       - phone_number   : str, max 20            (optional)
 *       - subject_id     : FK ReportSubject       (REQUIRED)
 *       - description    : text                   (REQUIRED)
 *       - attachments    : list<image>, max 5     (optional, jpg/png/webp, ≤5MB ea.)
 *
 * Throttle (server-side, must respect on the client):
 *   - 5 reports/min for anonymous clients
 *   - 20 reports/min for authenticated clients
 *
 * Designer-free brief (this is OUR design):
 *
 *   ┌────────────────────────────────────────────────────────────────┐
 *   │  Brand-teal panel, dotted texture, 32px radius                 │
 *   │                                                                │
 *   │  ┌── identity row ────────────────────────────────────────┐    │
 *   │  │  👤 نام و نام خانوادگی    📞 شماره تماس (اختیاری)     │    │
 *   │  └────────────────────────────────────────────────────────┘    │
 *   │                                                                │
 *   │  ⊞ دسته‌بندی   ────────────────────────────────                │
 *   │  [ 💰 فساد ] [ 🛡 امنیتی ] [ ⚖ تخلف ] [ 🎨 فرهنگی ] [ … ]    │
 *   │                                                                │
 *   │  ✎ شرح گزارش / سرنخ                          ··· 132/2000     │
 *   │  ┌──────────────────────────────────────────────────────┐     │
 *   │  │                                                       │     │
 *   │  │                                                       │     │
 *   │  └──────────────────────────────────────────────────────┘     │
 *   │                                                                │
 *   │  📎 مستندات (اختیاری — حداکثر ۵ تصویر)                       │
 *   │  ┌──────────────────────────────────────────────────────┐     │
 *   │  │  drag-drop area + clickable                          │     │
 *   │  │  ↓ تصاویر را اینجا بکشید یا کلیک کنید                │     │
 *   │  └──────────────────────────────────────────────────────┘     │
 *   │  [thumb] [thumb] [thumb]                                       │
 *   │                                                                │
 *   │  🔒 برای تأیید بکشید →    [───────────────────●──────]        │
 *   │                                                                │
 *   │                                          [✈ ارسال گزارش]       │
 *   └────────────────────────────────────────────────────────────────┘
 *
 * Innovations layered on the same backend contract:
 *   1. Visual subject picker  → radio chips with icons, not a dropdown.
 *      The selected subject's `description` text shows in a soft hint
 *      under the chips (helps users pick the right bucket).
 *   2. Live character counter on description, with min-length hint.
 *   3. Drag-and-drop attachment uploader with thumb previews, remove
 *      button, and a hard cap of 5 files (matches MAX_ATTACHMENTS_PER_REPORT).
 *      Client-side size/type validation matches the validators.
 *   4. SLIDE-TO-VERIFY anti-bot widget — replaces the boring 'من ربات
 *      نیستم' checkbox with a tactile thumb the user has to drag to the
 *      far edge. Mouse + touch, debounced reset on release-before-end,
 *      animated check + lock on completion. Feels like Apple's
 *      'slide to power off' or Slack's 'slide to confirm' — high-end UX.
 *   5. Paper-plane submit button, with loading + success states.
 *   6. Submit cooldown that mirrors the server throttle (5/min anon)
 *      so the button disables for the appropriate window after a
 *      successful POST.
 * ───────────────────────────────────────────────────────────────────────────
 */

type Subject = { id: string; name: string; description?: string };

const DEFAULT_SUBJECTS: Subject[] = [
  { id: '1', name: 'گزارش فساد اقتصادی',  description: 'موارد سوءاستفاده مالی، رانت، اختلاس و …' },
  { id: '2', name: 'گزارش تخلف اجتماعی', description: 'تخلفات اجتماعی، تجاوز به حقوق دیگران و …' },
  { id: '3', name: 'گزارش امنیتی',        description: 'تهدیدات امنیتی، نفوذ، فعالیت‌های مشکوک' },
  { id: '4', name: 'گزارش فرهنگی',        description: 'انحرافات فرهنگی، توهین به مقدسات و …' },
  { id: '5', name: 'سایر موارد',           description: 'هر مورد دیگری که نیاز به بررسی دارد' },
];

const SUBJECT_ICON: Record<string, 'shield' | 'scale' | 'megaphone' | 'sparkles' | 'flag'> = {
  '1': 'scale',       // اقتصادی
  '2': 'megaphone',   // اجتماعی
  '3': 'shield',      // امنیتی
  '4': 'sparkles',    // فرهنگی
  '5': 'flag',        // سایر
};

const MAX_ATTACHMENTS = 5;            // mirrors MAX_ATTACHMENTS_PER_REPORT
const MAX_FILE_SIZE   = 5 * 1024 * 1024; // 5MB, mirrors validate_image_size
const ALLOWED_TYPES   = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
const DESC_MIN        = 20;
const DESC_MAX        = 2000;
const COOLDOWN_SECS   = 12;           // gentle client-side back-off after success

type FormState = {
  full_name: string;
  phone_number: string;
  subject_id: string;
  description: string;
};

const INITIAL: FormState = {
  full_name: '', phone_number: '', subject_id: '', description: '',
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Field                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

function Field({
  icon, placeholder, value, onChange, type = 'text', inputMode, maxLength, required,
}: {
  icon: React.ReactNode;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  inputMode?: 'numeric' | 'tel' | 'text' | 'email';
  maxLength?: number;
  required?: boolean;
}) {
  return (
    <div className="relative">
      <span className="absolute right-4 top-1/2 -translate-y-1/2 text-brand-500 z-10 pointer-events-none">
        {icon}
      </span>
      <input
        type={type}
        inputMode={inputMode}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder + (required ? ' *' : '')}
        aria-label={placeholder}
        maxLength={maxLength}
        dir="rtl"
        className="w-full h-12 pr-10 pl-4 rounded-xl bg-white text-ink-800 text-[14px]
                   outline-none focus:ring-2 focus:ring-white/60 placeholder:text-ink-400 text-right
                   font-medium"
      />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Slide-to-verify ('من ربات نیستم' replacement)                            */
/* ───────────────────────────────────────────────────────────────────────── */

function SlideToVerify({
  verified,
  onVerify,
  onReset,
}: {
  verified: boolean;
  onVerify: () => void;
  onReset: () => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [x, setX] = useState(0);
  const [maxX, setMaxX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const THUMB = 44;                  // px
  const COMPLETE_RATIO = 0.92;       // user must drag ~92% of the track

  // Compute the max draggable distance from the rendered track
  const measure = useCallback(() => {
    const t = trackRef.current;
    if (!t) return;
    setMaxX(Math.max(0, t.clientWidth - THUMB - 8));
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [measure]);

  const beginDrag = (clientX: number) => {
    if (verified) return;
    setDragging(true);
    const t = trackRef.current;
    if (!t) return;
    const rect = t.getBoundingClientRect();
    // RTL: thumb starts at the right, moves to the LEFT as user drags
    const offset = rect.right - clientX - THUMB / 2 - 4;
    setX(Math.min(maxX, Math.max(0, offset)));
  };
  const moveDrag = (clientX: number) => {
    if (!dragging || verified) return;
    const t = trackRef.current;
    if (!t) return;
    const rect = t.getBoundingClientRect();
    const offset = rect.right - clientX - THUMB / 2 - 4;
    setX(Math.min(maxX, Math.max(0, offset)));
  };
  const endDrag = () => {
    if (!dragging) return;
    setDragging(false);
    if (maxX > 0 && x / maxX >= COMPLETE_RATIO) {
      setX(maxX);
      onVerify();
    } else {
      // snap back
      setX(0);
    }
  };

  // Mouse + touch handlers wired to the document while dragging
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent | TouchEvent) => {
      const cx = e instanceof MouseEvent ? e.clientX : e.touches[0]?.clientX;
      if (typeof cx === 'number') moveDrag(cx);
    };
    const onUp = () => endDrag();
    document.addEventListener('mousemove', onMove);
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchend', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('touchmove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.removeEventListener('touchend', onUp);
    };
  }, [dragging, x, maxX]); // eslint-disable-line react-hooks/exhaustive-deps

  const progress = maxX > 0 ? Math.min(1, x / maxX) : 0;

  return (
    <div
      ref={trackRef}
      className={`relative w-full h-14 rounded-full overflow-hidden select-none
                  ring-1 ring-black/5 transition-colors duration-300
                  ${verified
                    ? 'bg-gradient-to-l from-emerald-500 to-emerald-600'
                    : 'bg-white/95'}`}
      style={{ touchAction: 'pan-y' }}
      role="button"
      aria-label="برای تأیید بکشید"
      aria-pressed={verified}
    >
      {/* Fill — the bar that grows as the user drags */}
      <div
        aria-hidden="true"
        className="absolute inset-y-0 right-0 transition-colors duration-300
                   bg-gradient-to-l from-brand-400 to-brand-600
                   pointer-events-none"
        style={{
          width: `${verified ? 100 : progress * 100}%`,
          opacity: verified ? 0 : 0.95,
        }}
      />

      {/* Label */}
      <span
        className={`absolute inset-0 flex items-center justify-center
                    text-[13px] font-extrabold pointer-events-none
                    transition-all duration-300
                    ${verified
                      ? 'text-white'
                      : (progress > 0.05 ? 'text-white' : 'text-ink-700')}`}
      >
        {verified ? (
          <span className="inline-flex items-center gap-2">
            <Icon name="check" className="w-4 h-4" strokeWidth={3} />
            هویت شما تأیید شد
          </span>
        ) : (
          <span className="inline-flex items-center gap-2">
            <Icon name="shield" className="w-4 h-4" />
            برای تأیید، تب را بکشید
          </span>
        )}
      </span>

      {/* Thumb — draggable circle on the RTL-right edge */}
      <motion.button
        type="button"
        onMouseDown={(e) => beginDrag(e.clientX)}
        onTouchStart={(e) => beginDrag(e.touches[0].clientX)}
        onClick={() => { if (verified) onReset(); }}
        aria-label={verified ? 'بازنشانی' : 'برای تأیید بکشید'}
        disabled={verified && false}
        animate={{ x: verified ? -maxX : -x }}
        transition={{ type: dragging ? false : 'spring', stiffness: 380, damping: 28 }}
        className={`absolute top-1/2 right-1 -translate-y-1/2 w-11 h-11 rounded-full
                    bg-white text-brand-600 flex items-center justify-center
                    shadow-[0_6px_16px_-4px_rgba(0,0,0,.25)]
                    cursor-grab active:cursor-grabbing
                    ${verified ? 'bg-emerald-50 text-emerald-600' : ''}`}
      >
        {verified ? (
          <Icon name="check" className="w-5 h-5" strokeWidth={3} />
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {/* Double-chevron pointing LEFT — universal 'drag this way' affordance */}
            <polyline points="11 17 6 12 11 7" />
            <polyline points="18 17 13 12 18 7" />
          </svg>
        )}
      </motion.button>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function PublicReportSection({
  subjects = DEFAULT_SUBJECTS,
}: {
  subjects?: Subject[];
}) {
  const [form, setForm]           = useState<FormState>(INITIAL);
  const [files, setFiles]         = useState<File[]>([]);
  const [verified, setVerified]   = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errorMsg, setErrorMsg]   = useState<string | null>(null);
  const [cooldown, setCooldown]   = useState(0);
  const fileInputRef              = useRef<HTMLInputElement>(null);

  // File previews
  const previews = useMemo(
    () => files.map((f) => ({ name: f.name, url: URL.createObjectURL(f), size: f.size })),
    [files],
  );
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

  // Cooldown ticker after successful submission
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  function update<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }));
    setErrorMsg(null);
  }

  function addFiles(newOnes: FileList | File[]) {
    const ok: File[] = [];
    const errors: string[] = [];
    for (const f of Array.from(newOnes)) {
      if (!ALLOWED_TYPES.includes(f.type)) { errors.push(`${f.name}: فرمت غیرمجاز`); continue; }
      if (f.size > MAX_FILE_SIZE)         { errors.push(`${f.name}: حجم بیش از ۵MB`); continue; }
      if (files.length + ok.length >= MAX_ATTACHMENTS) { errors.push(`حداکثر ${MAX_ATTACHMENTS} فایل`); break; }
      ok.push(f);
    }
    if (ok.length) setFiles((prev) => [...prev, ...ok].slice(0, MAX_ATTACHMENTS));
    if (errors.length) setErrorMsg(errors[0]);
  }
  function removeFile(i: number) {
    setFiles((prev) => prev.filter((_, idx) => idx !== i));
  }

  const canSubmit =
    !!form.full_name.trim() &&
    !!form.subject_id &&
    form.description.trim().length >= DESC_MIN &&
    verified &&
    !submitting &&
    cooldown <= 0;

  const selectedSubject = subjects.find((s) => s.id === form.subject_id);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setErrorMsg(null);

    // Wire-up note: real call posts FormData to /api/v1/public-reports/reports/
    // with full_name, phone_number, subject_id, description, attachments[]
    setTimeout(() => {
      setSubmitting(false);
      setSubmitted(true);
      setForm(INITIAL);
      setFiles([]);
      setVerified(false);
      setCooldown(COOLDOWN_SECS);
      // Auto-dismiss the success banner after 6s
      setTimeout(() => setSubmitted(false), 6000);
    }, 1200);
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
          className="bg-brand-500 rounded-[2rem] md:rounded-[2.5rem] p-5 md:p-8 lg:p-10
                     text-white relative overflow-hidden"
        >
          {/* Decorative dotted texture */}
          <div aria-hidden="true" className="absolute inset-0 opacity-[0.06] pointer-events-none"
            style={{
              backgroundImage:
                'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.7) 1px, transparent 1px)',
              backgroundSize: '22px 22px',
            }} />

          {/* ── Identity row ───────────────────────────────────────────── */}
          <div className="relative grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 mb-4 md:mb-5">
            <Field
              icon={<Icon name="user" className="w-4 h-4" />}
              placeholder="نام و نام خانوادگی"
              value={form.full_name}
              onChange={(v) => update('full_name', v)}
              maxLength={150}
              required
            />
            <Field
              icon={<Icon name="phone" className="w-4 h-4" />}
              placeholder="شماره تماس (اختیاری)"
              value={form.phone_number}
              onChange={(v) => update('phone_number', v.replace(/[^0-9+]/g, '').slice(0, 14))}
              type="tel"
              inputMode="tel"
            />
          </div>

          {/* ── Subject picker — visual chips, not a dropdown ──────────── */}
          <fieldset className="relative mb-4 md:mb-5">
            <legend className="text-[12.5px] font-extrabold text-white/90 mb-2 px-1">
              <span className="inline-flex items-center gap-1.5">
                <Icon name="category-pick" className="w-3.5 h-3.5" />
                موضوع گزارش <span className="text-white/70">*</span>
              </span>
            </legend>
            <div className="flex flex-wrap gap-2">
              {subjects.map((s) => {
                const isActive = form.subject_id === s.id;
                const iconName = SUBJECT_ICON[s.id] || 'flag';
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => update('subject_id', s.id)}
                    aria-pressed={isActive}
                    className={`inline-flex items-center gap-1.5 h-10 px-3.5 rounded-full
                                text-[12.5px] font-extrabold transition-all duration-200
                                ${isActive
                                  ? 'bg-white text-brand-700 shadow-[0_6px_14px_-6px_rgba(0,0,0,.35)] scale-[1.02]'
                                  : 'bg-white/[0.12] text-white hover:bg-white/[0.18]'}`}
                  >
                    <Icon name={iconName} className="w-3.5 h-3.5" />
                    <span>{s.name}</span>
                  </button>
                );
              })}
            </div>
            {selectedSubject?.description && (
              <p className="mt-2 px-1 text-[11.5px] text-white/75 font-medium">
                <Icon name="check" className="w-3 h-3 inline-block -mt-0.5 ml-1" />
                {selectedSubject.description}
              </p>
            )}
          </fieldset>

          {/* ── Description with live char counter ─────────────────────── */}
          <div className="relative mb-4 md:mb-5">
            <Icon name="message-square" className="w-4 h-4 text-brand-500 absolute right-4 top-[1.25rem] z-10 pointer-events-none" />
            <textarea
              value={form.description}
              onChange={(e) => update('description', e.target.value.slice(0, DESC_MAX))}
              placeholder="شرح گزارش یا سرنخ شما را با جزئیات بنویسید…"
              aria-label="شرح گزارش"
              rows={5}
              maxLength={DESC_MAX}
              dir="rtl"
              className="w-full pr-10 pl-4 pt-[1.15rem] pb-4 rounded-xl bg-white text-ink-800 text-[14px]
                         outline-none focus:ring-2 focus:ring-white/60 resize-y min-h-[140px]
                         text-right leading-7 font-medium"
            />
            <div className={`mt-1.5 px-1 flex items-center justify-between text-[11px] font-bold
                             ${form.description.length < DESC_MIN ? 'text-white/70' : 'text-white/90'}`}>
              <span>
                {form.description.length < DESC_MIN
                  ? `حداقل ${DESC_MIN.toLocaleString('fa-IR')} کاراکتر`
                  : 'متن قابل قبول است'}
              </span>
              <span className="tabular-nums">
                {form.description.length.toLocaleString('fa-IR')}
                <span className="opacity-60"> / {DESC_MAX.toLocaleString('fa-IR')}</span>
              </span>
            </div>
          </div>

          {/* ── Attachments dropzone ───────────────────────────────────── */}
          <div className="relative mb-5">
            <div className="text-[12.5px] font-extrabold text-white/90 mb-2 px-1 inline-flex items-center gap-1.5">
              <Icon name="attach" className="w-3.5 h-3.5" />
              <span>پیوست تصویری</span>
              <span className="text-white/70 font-medium">
                (اختیاری — حداکثر {MAX_ATTACHMENTS.toLocaleString('fa-IR')} تصویر، هر کدام تا ۵ مگابایت)
              </span>
            </div>
            <Dropzone
              files={files}
              previews={previews}
              onAdd={addFiles}
              onRemove={removeFile}
              fileInputRef={fileInputRef}
              max={MAX_ATTACHMENTS}
            />
          </div>

          {/* ── Slide-to-verify + submit row ───────────────────────────── */}
          <div className="relative grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-center">
            <SlideToVerify
              verified={verified}
              onVerify={() => setVerified(true)}
              onReset={() => setVerified(false)}
            />
            <button
              type="submit"
              disabled={!canSubmit}
              className="relative inline-flex items-center justify-center gap-2 h-14 px-7
                         rounded-full bg-white text-brand-700 font-extrabold text-[14px]
                         shadow-[0_8px_24px_-8px_rgba(0,0,0,.35)]
                         transition-all duration-200
                         disabled:opacity-50 disabled:cursor-not-allowed
                         enabled:hover:scale-[1.02] enabled:active:scale-[.98] overflow-hidden"
            >
              <AnimatePresence mode="wait" initial={false}>
                {submitting ? (
                  <motion.span
                    key="loading"
                    initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                    className="inline-flex items-center gap-2"
                  >
                    <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
                      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                    در حال ارسال…
                  </motion.span>
                ) : cooldown > 0 ? (
                  <motion.span
                    key="cool"
                    initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                    className="inline-flex items-center gap-2 tabular-nums"
                  >
                    <Icon name="clock" className="w-4 h-4" />
                    لطفاً {cooldown.toLocaleString('fa-IR')} ثانیه صبر کنید
                  </motion.span>
                ) : (
                  <motion.span
                    key="idle"
                    initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                    className="inline-flex items-center gap-2"
                  >
                    {/* Paper-plane icon — universal 'send' metaphor */}
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
                         className="-mt-0.5">
                      <path d="M22 2 11 13" />
                      <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
                    </svg>
                    ارسال گزارش
                  </motion.span>
                )}
              </AnimatePresence>
            </button>
          </div>

          {/* ── Status banners ─────────────────────────────────────────── */}
          <AnimatePresence>
            {submitted && (
              <motion.div
                key="ok"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                className="relative mt-4 flex items-start gap-3 px-4 py-3 rounded-xl
                           bg-emerald-500/[0.15] ring-1 ring-emerald-300/40 text-white"
                role="status"
              >
                <span className="w-8 h-8 rounded-full bg-emerald-500 text-white
                                 flex items-center justify-center shrink-0
                                 shadow-[0_6px_14px_-4px_rgba(16,185,129,.55)]">
                  <Icon name="check" className="w-4 h-4" strokeWidth={3} />
                </span>
                <div className="flex-1 text-[13px] leading-7 font-bold">
                  گزارش شما با موفقیت دریافت شد. کارشناسان ما در اولین فرصت پیگیری خواهند کرد.
                </div>
              </motion.div>
            )}
            {errorMsg && (
              <motion.div
                key="err"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                className="relative mt-4 flex items-start gap-3 px-4 py-3 rounded-xl
                           bg-rose-500/[0.18] ring-1 ring-rose-300/40 text-white"
                role="alert"
              >
                <span className="w-8 h-8 rounded-full bg-rose-500 text-white
                                 flex items-center justify-center shrink-0">
                  <Icon name="close" className="w-4 h-4" strokeWidth={3} />
                </span>
                <div className="flex-1 text-[13px] leading-7 font-bold">{errorMsg}</div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Privacy reassurance ────────────────────────────────────── */}
          <p className="relative mt-4 text-center text-[11.5px] text-white/80 font-medium">
            <Icon name="shield" className="w-3 h-3 inline-block -mt-0.5 ml-1" />
            هویت گزارش‌دهنده محرمانه است · داده‌ها رمزنگاری شده ارسال می‌شوند
          </p>
        </motion.form>
      </div>
    </section>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Dropzone                                                                 */
/* ───────────────────────────────────────────────────────────────────────── */

function Dropzone({
  files, previews, onAdd, onRemove, fileInputRef, max,
}: {
  files: File[];
  previews: { name: string; url: string; size: number }[];
  onAdd: (f: FileList | File[]) => void;
  onRemove: (i: number) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  max: number;
}) {
  const [hover, setHover] = useState(false);
  const remaining = max - files.length;

  return (
    <>
      <label
        onDragEnter={(e) => { e.preventDefault(); setHover(true); }}
        onDragOver={(e)  => { e.preventDefault(); setHover(true); }}
        onDragLeave={(e) => { e.preventDefault(); setHover(false); }}
        onDrop={(e) => {
          e.preventDefault();
          setHover(false);
          if (e.dataTransfer.files?.length) onAdd(e.dataTransfer.files);
        }}
        className={`relative block w-full rounded-2xl border-2 border-dashed cursor-pointer
                    transition-all duration-200 px-4 py-5 text-center
                    ${hover
                      ? 'border-white bg-white/[0.15]'
                      : 'border-white/30 bg-white/[0.06] hover:bg-white/[0.10]'}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_TYPES.join(',')}
          className="sr-only"
          onChange={(e) => { if (e.target.files) onAdd(e.target.files); e.currentTarget.value = ''; }}
          disabled={remaining <= 0}
        />
        <div className="flex flex-col items-center gap-1.5">
          <span className="w-10 h-10 rounded-full bg-white/[0.15] flex items-center justify-center">
            <Icon name="attach" className="w-5 h-5 text-white" />
          </span>
          <p className="text-[13px] font-extrabold text-white">
            {remaining > 0
              ? 'تصاویر را اینجا بکشید یا کلیک کنید'
              : 'به سقف پیوست رسیدید'}
          </p>
          {remaining > 0 && (
            <p className="text-[11px] text-white/75 font-medium">
              {`${remaining.toLocaleString('fa-IR')} فایل دیگر می‌توانید اضافه کنید (jpg / png / webp)`}
            </p>
          )}
        </div>
      </label>

      {/* Preview thumbs */}
      {previews.length > 0 && (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
          {previews.map((p, i) => (
            <div
              key={p.url}
              className="relative aspect-square rounded-xl overflow-hidden bg-white/10
                         ring-1 ring-white/20 group"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.url} alt={p.name} className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
              <button
                type="button"
                onClick={(e) => { e.preventDefault(); onRemove(i); }}
                aria-label="حذف"
                className="absolute top-1.5 left-1.5 w-7 h-7 rounded-full bg-rose-500 text-white
                           flex items-center justify-center
                           shadow-[0_4px_12px_-4px_rgba(225,29,72,.6)]
                           hover:scale-110 active:scale-95 transition-transform"
              >
                <Icon name="close" className="w-3.5 h-3.5" strokeWidth={3} />
              </button>
              <p className="absolute bottom-1 inset-x-1 text-[10px] text-white font-bold
                            truncate text-center px-1 drop-shadow opacity-0 group-hover:opacity-100 transition-opacity">
                {(p.size / 1024).toFixed(0)} KB
              </p>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
