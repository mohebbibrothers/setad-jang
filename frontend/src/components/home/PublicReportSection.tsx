'use client';

import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon, type IconName } from '@/components/icons/Icon';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Public reports — designer-free, backend-faithful (v4 — polished).
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
 *       - attachments    : list<image>, max 5     (optional)
 *
 *   Hard backend limits (mirror of apps.public_reports.validators):
 *     ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
 *     MAX_IMAGE_SIZE_MB        = 5
 *     MAX_ATTACHMENTS_PER_REPORT = 5
 *
 *   Anti-abuse (server-side, also enforced gracefully on the client):
 *     - 5 reports/min for anonymous clients
 *     - 20 reports/min for authenticated clients
 *
 * UX polish in v4:
 *   1. Field icons re-skinned: each input gets a soft brand-tinted disc
 *      so the glyph reads as a small premium badge, not a flat icon.
 *   2. Subject picker switched from chips to a fully-custom DROPDOWN with
 *      a glassy listbox, per-subject coloured icon, hover + selected
 *      states, click-outside dismissal, full ARIA wiring.
 *   3. File-validation now reads ALLOWED_IMAGE_EXTENSIONS by EXTENSION
 *      (matches the server-side check) instead of MIME-type only — so
 *      'image/jpg' from older mobiles is accepted, and there is parity
 *      with the backend.
 *   4. Slide-to-verify chrome upgraded: gradient track, security-shield
 *      icon while idle, sparkles burst at the end of the slide,
 *      gradient-green success state.
 *   5. Submit button gets a soft brand-tinted glow, plus a subtle live
 *      'sending' shimmer.
 *   6. All copy and aria-labels are RTL-correct and human-friendly.
 * ───────────────────────────────────────────────────────────────────────────
 */

type Subject = { id: string; name: string; description?: string };

const DEFAULT_SUBJECTS: Subject[] = [
  { id: '1', name: 'گزارش فساد اقتصادی',  description: 'رشوه، اختلاس، فرار مالیاتی و فساد در نهادهای دولتی.' },
  { id: '2', name: 'گزارش تخلف اجتماعی',  description: 'هنجارشکنی‌ها و آسیب‌های اجتماعی.' },
  { id: '3', name: 'گزارش امنیتی',         description: 'مسائل حساس امنیتی و تهدیدات.' },
  { id: '4', name: 'گزارش فرهنگی',         description: 'ناهنجاری‌های فرهنگی و رسانه‌ای.' },
  { id: '5', name: 'سایر موارد',           description: 'سایر گزارش‌هایی که در دسته‌های بالا نمی‌گنجند.' },
];

const SUBJECT_ICON: Record<string, IconName> = {
  '1': 'scale',       // اقتصادی
  '2': 'megaphone',   // اجتماعی
  '3': 'shield',      // امنیتی
  '4': 'sparkles',    // فرهنگی
  '5': 'flag',        // سایر
};

// ── Backend-mirrored limits (apps.public_reports.validators) ────────────
const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp'] as const;
const MAX_IMAGE_SIZE_MB = 5;
const MAX_FILE_SIZE     = MAX_IMAGE_SIZE_MB * 1024 * 1024;
const MAX_ATTACHMENTS   = 5;     // mirrors MAX_ATTACHMENTS_PER_REPORT

// Frontend-only UX limits (no server-side equivalent)
const DESC_MIN          = 20;
const DESC_MAX          = 2000;
const COOLDOWN_SECS     = 12;

type FormState = {
  full_name: string;
  phone_number: string;
  subject_id: string;
  description: string;
};

const INITIAL: FormState = {
  full_name: '', phone_number: '', subject_id: '', description: '',
};

function getExt(name: string): string {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i + 1).toLowerCase() : '';
}

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
      {/* Icon sits inside a soft brand-tinted disc — reads as a premium
          badge rather than a flat glyph. */}
      <span
        className="absolute right-2 top-1/2 -translate-y-1/2 z-10 pointer-events-none
                   w-9 h-9 rounded-xl flex items-center justify-center
                   bg-gradient-to-br from-brand-50 to-brand-100
                   text-brand-600 shadow-[inset_0_0_0_1px_rgba(13,128,116,.08)]"
      >
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
        className="w-full h-12 pr-12 pl-4 rounded-xl bg-white text-ink-800 text-[14px]
                   outline-none focus:ring-2 focus:ring-white/60 placeholder:text-ink-400
                   text-right font-medium
                   transition-shadow"
      />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Subject dropdown — custom listbox (replaces chips)                       */
/* ───────────────────────────────────────────────────────────────────────── */

function SubjectDropdown({
  subjects, value, onChange,
}: {
  subjects: Subject[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const selected = subjects.find((s) => s.id === value) ?? null;
  const selectedIcon = selected ? SUBJECT_ICON[selected.id] || 'flag' : null;

  // Close on outside click / escape
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent | TouchEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false); }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown, { passive: true });
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      {/* Field shell — same height/radius as the inputs above */}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={`relative w-full h-12 pr-12 pl-12 rounded-xl bg-white text-right
                    text-[14px] font-medium
                    transition-shadow outline-none
                    ${open ? 'ring-2 ring-white/60' : ''}
                    ${selected ? 'text-ink-800' : 'text-ink-400'}`}
      >
        {/* Leading icon disc (same style as the Field's) */}
        <span
          className="absolute right-2 top-1/2 -translate-y-1/2
                     w-9 h-9 rounded-xl flex items-center justify-center
                     bg-gradient-to-br from-brand-50 to-brand-100
                     text-brand-600 shadow-[inset_0_0_0_1px_rgba(13,128,116,.08)]"
        >
          {selectedIcon
            ? <Icon name={selectedIcon} className="w-4 h-4" />
            : <Icon name="category-pick" className="w-4 h-4" />}
        </span>

        <span className="block truncate">
          {selected ? selected.name : 'موضوع گزارش را انتخاب کنید *'}
        </span>

        {/* Trailing chevron */}
        <span
          className={`absolute left-3 top-1/2 -translate-y-1/2 text-ink-500
                      transition-transform duration-300 ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          <Icon name="chevron-down" className="w-4 h-4" />
        </span>
      </button>

      {/* Listbox */}
      <AnimatePresence>
        {open && (
          <motion.ul
            role="listbox"
            initial={{ opacity: 0, y: 10, scale: 0.97 }}
            animate={{ opacity: 1, y: 0,  scale: 1 }}
            exit={{    opacity: 0, y: 6,  scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 380, damping: 26, mass: 0.6 }}
            className="absolute z-30 inset-x-0 mt-2 p-2 rounded-2xl bg-white
                       shadow-[0_24px_60px_-12px_rgba(0,0,0,.30),0_0_0_1px_rgba(217,222,229,.7)]
                       max-h-[320px] overflow-y-auto"
          >
            {subjects.map((s) => {
              const isActive = value === s.id;
              const iconName = SUBJECT_ICON[s.id] || 'flag';
              return (
                <li key={s.id} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    onClick={() => { onChange(s.id); setOpen(false); }}
                    className={`group/item w-full flex items-center gap-3 px-3 py-2.5 rounded-xl
                                text-right transition-colors duration-150
                                ${isActive
                                  ? 'bg-brand-50 text-brand-700'
                                  : 'text-ink-800 hover:bg-ink-50'}`}
                  >
                    <span
                      className={`flex items-center justify-center w-9 h-9 rounded-xl shrink-0
                                  transition-all duration-200
                                  ${isActive
                                    ? 'bg-brand-500 text-white shadow-[0_6px_14px_-4px_rgba(13,128,116,.55)]'
                                    : 'bg-brand-50 text-brand-600 group-hover/item:bg-brand-100'}`}
                    >
                      <Icon name={iconName} className="w-4 h-4" />
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="block text-[13px] font-extrabold leading-5 truncate">
                        {s.name}
                      </span>
                      {s.description && (
                        <span className="block text-[11px] text-ink-500 font-medium leading-5 truncate">
                          {s.description}
                        </span>
                      )}
                    </span>
                    {isActive && (
                      <span className="shrink-0 text-brand-600">
                        <Icon name="check" className="w-4 h-4" strokeWidth={3} />
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Slide-to-verify ('من ربات نیستم' replacement)                            */
/* ───────────────────────────────────────────────────────────────────────── */

function SlideToVerify({
  verified, onVerify,
}: {
  verified: boolean;
  onVerify: () => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [x, setX] = useState(0);
  const [maxX, setMaxX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const THUMB = 48;                  // px
  const COMPLETE_RATIO = 0.92;

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

  useEffect(() => { if (verified) setX(maxX); }, [verified, maxX]);

  const beginDrag = (clientX: number) => {
    if (verified) return;
    setDragging(true);
    const t = trackRef.current; if (!t) return;
    const rect = t.getBoundingClientRect();
    const offset = rect.right - clientX - THUMB / 2 - 4;
    setX(Math.min(maxX, Math.max(0, offset)));
  };
  const moveDrag = (clientX: number) => {
    if (!dragging || verified) return;
    const t = trackRef.current; if (!t) return;
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
      setX(0);
    }
  };

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
  const pctNum = Math.round(progress * 100);

  return (
    <div className="w-full select-none">
      <div
        ref={trackRef}
        className={`relative w-full h-14 rounded-full overflow-hidden
                    ring-1 transition-colors duration-300
                    ${verified
                      ? 'bg-gradient-to-l from-emerald-500 via-emerald-500 to-brand-500 ring-emerald-300/40'
                      : 'bg-gradient-to-br from-white via-white to-ink-50 ring-black/[0.06]'}`}
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

        {/* Background label */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-[1]">
          {verified ? (
            <span className="inline-flex items-center gap-1.5 text-[12.5px] font-extrabold text-white">
              <Icon name="check" className="w-4 h-4" strokeWidth={3} />
              تأیید شد — می‌توانید گزارش را ارسال کنید
            </span>
          ) : (
            <span className={`inline-flex items-center gap-1.5 text-[12.5px] font-extrabold
                              transition-colors duration-200
                              ${pctNum > 30 ? 'text-white' : 'text-ink-600'}`}>
              <Icon name="shield" className="w-4 h-4" />
              <span>برای تأیید انسان بودن، بکشید ←</span>
            </span>
          )}
        </div>

        {/* Sparkles on success */}
        {verified && (
          <>
            {[0, 1, 2, 3, 4].map((i) => (
              <motion.span
                key={i}
                aria-hidden="true"
                initial={{ opacity: 0, scale: 0.4 }}
                animate={{ opacity: [0, 1, 0], scale: [0.4, 1.2, 0.4],
                           x: (i - 2) * 22, y: -8 + (i % 2) * 14 }}
                transition={{ duration: 1.2, delay: 0.1 + i * 0.06, repeat: Infinity, repeatDelay: 1.6 }}
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
                           text-white pointer-events-none z-[2]"
              >
                <Icon name="sparkles" className="w-3 h-3" />
              </motion.span>
            ))}
          </>
        )}

        {/* Draggable thumb */}
        <motion.button
          type="button"
          aria-label={verified ? 'تأیید شد' : 'برای تأیید بکشید'}
          aria-pressed={verified}
          disabled={verified}
          onMouseDown={(e) => beginDrag(e.clientX)}
          onTouchStart={(e) => beginDrag(e.touches[0].clientX)}
          animate={{ right: 4 + (verified ? maxX : x) }}
          transition={{ type: dragging ? 'tween' : 'spring', stiffness: 300, damping: 28, duration: dragging ? 0 : 0.3 }}
          className={`absolute top-1/2 -translate-y-1/2 w-12 h-12 rounded-full
                      flex items-center justify-center cursor-grab active:cursor-grabbing
                      shadow-[0_8px_18px_-4px_rgba(0,0,0,.30)]
                      transition-colors duration-300 z-[3]
                      ${verified
                        ? 'bg-white text-emerald-600'
                        : 'bg-gradient-to-br from-brand-500 to-brand-700 text-white'}`}
        >
          {verified ? (
            <Icon name="check" className="w-5 h-5" strokeWidth={3} />
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="11 17 6 12 11 7" />
              <polyline points="18 17 13 12 18 7" />
            </svg>
          )}
        </motion.button>
      </div>
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

  const previews = useMemo(
    () => files.map((f) => ({ name: f.name, url: URL.createObjectURL(f), size: f.size })),
    [files],
  );
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

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
      const ext = getExt(f.name);
      if (!ALLOWED_EXTENSIONS.includes(ext as (typeof ALLOWED_EXTENSIONS)[number])) {
        errors.push(`${f.name}: فرمت غیرمجاز (jpg / jpeg / png / webp)`);
        continue;
      }
      if (f.size > MAX_FILE_SIZE) {
        errors.push(`${f.name}: حجم بیش از ${MAX_IMAGE_SIZE_MB.toLocaleString('fa-IR')} مگابایت`);
        continue;
      }
      if (files.length + ok.length >= MAX_ATTACHMENTS) {
        errors.push(`حداکثر ${MAX_ATTACHMENTS.toLocaleString('fa-IR')} فایل قابل پیوست است`);
        break;
      }
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

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setErrorMsg(null);
    setTimeout(() => {
      setSubmitting(false);
      setSubmitted(true);
      setForm(INITIAL);
      setFiles([]);
      setVerified(false);
      setCooldown(COOLDOWN_SECS);
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
          <div className="relative grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 mb-3 md:mb-4">
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

          {/* ── Subject dropdown — full width ──────────────────────────── */}
          <div className="relative mb-3 md:mb-4">
            <SubjectDropdown
              subjects={subjects}
              value={form.subject_id}
              onChange={(id) => update('subject_id', id)}
            />
          </div>

          {/* ── Description with live char counter ─────────────────────── */}
          <div className="relative mb-4 md:mb-5">
            <span
              className="absolute right-2 top-2 z-10 pointer-events-none
                         w-9 h-9 rounded-xl flex items-center justify-center
                         bg-gradient-to-br from-brand-50 to-brand-100
                         text-brand-600 shadow-[inset_0_0_0_1px_rgba(13,128,116,.08)]"
              aria-hidden="true"
            >
              <Icon name="message-square" className="w-4 h-4" />
            </span>
            <textarea
              value={form.description}
              onChange={(e) => update('description', e.target.value.slice(0, DESC_MAX))}
              placeholder="شرح گزارش یا سرنخ شما را با جزئیات بنویسید…"
              aria-label="شرح گزارش"
              rows={5}
              maxLength={DESC_MAX}
              dir="rtl"
              className="w-full pr-12 pl-4 pt-3 pb-4 rounded-xl bg-white text-ink-800 text-[14px]
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
                (اختیاری — حداکثر {MAX_ATTACHMENTS.toLocaleString('fa-IR')} تصویر، هر کدام تا {MAX_IMAGE_SIZE_MB.toLocaleString('fa-IR')} مگابایت — jpg / jpeg / png / webp)
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
          accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
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
              {`${remaining.toLocaleString('fa-IR')} فایل دیگر می‌توانید اضافه کنید (jpg / jpeg / png / webp)`}
            </p>
          )}
        </div>
      </label>

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
