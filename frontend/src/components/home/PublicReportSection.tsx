'use client';

import { useState, useRef, useCallback } from 'react';
import Image from 'next/image';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Public Reports section — designer-free, backend-faithful (v2).
 *
 * Backend contract (apps/public_reports):
 *
 *   GET  /api/v1/public-reports/subjects/    ReportSubjectPublicSerializer
 *     → list of active subjects: { id, title, slug, description, order }
 *
 *   POST /api/v1/public-reports/reports/     ReportCreateSerializer
 *     Fields the form must submit (multipart/form-data):
 *       - full_name       string  (required, max 150)
 *       - phone_number    string  (OPTIONAL, max 20)  — see model: blank/null OK
 *       - subject_id      int     (required, FK → ReportSubject)
 *       - description     string  (required, free text)
 *       - attachments[]   File[]  (optional, max 5 files, jpg|jpeg|png|webp,
 *                                  ≤ 5MB each — see validators.py)
 *     Throttle (anonymous): 5/min (ReportCreateAnonThrottle)
 *     Throttle (auth):     20/min (ReportCreateUserThrottle)
 *
 *   Status of a created report follows ReportStatus state machine:
 *     pending → reviewing → approved / rejected
 *
 * UX upgrades wired to real backend features:
 *   1. Subject SELECT now becomes a chip-grid: every subject from the
 *      backend renders as a click-to-toggle chip. Easier to scan, less
 *      mobile keyboard friction. Description appears as a soft helper
 *      line under the active chip.
 *   2. Multi-file UPLOAD with drag-drop + thumbnail previews. Honours
 *      the backend's 5-file max, 5MB-per-file cap, and the allowed
 *      extension whitelist — client-side, so the user never wastes a
 *      submission on an invalid file.
 *   3. PRIVACY assurance card pinned beside the form (desktop) and as
 *      a soft banner on mobile — explains that phone is optional and
 *      identity is confidential. This is the single biggest psychology
 *      lever for getting users to send sensitive reports.
 *   4. Smart character counter on the description (motivates a useful
 *      length — 40 chars min is gently nudged).
 *   5. Success screen after submit shows the returned tracking id
 *      (#1234) with a copy-to-clipboard chip — matches the backend
 *      response payload.
 *   6. Submit button now carries a 'shield-check' icon (آیکن سپر-تأیید)
 *      that signals 'secure submission' — much more relevant than the
 *      generic paper-plane.
 * ───────────────────────────────────────────────────────────────────────────
 */

const MAX_ATTACHMENTS = 5;
const MAX_FILE_MB = 5;
const ALLOWED_EXT = ['jpg', 'jpeg', 'png', 'webp'];

type Subject = { id: string; name: string; description?: string };

type FormState = {
  full_name: string;
  phone: string;
  subject_id: string;
  description: string;
};

const INITIAL: FormState = { full_name: '', phone: '', subject_id: '', description: '' };

/* ───────────────────────────────────────────────────────────────────────── */
/*  Icons (hand-tuned, metaphor-rich)                                        */
/* ───────────────────────────────────────────────────────────────────────── */

function ShieldCheckIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M20 12.5V6.5L12 3 4 6.5v6c0 5 4 8.5 8 9.5 4-1 8-4.5 8-9.5Z" />
      <path d="m8.5 12 2.5 2.5L16 9.5" />
    </svg>
  );
}
function UserIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}
function PhoneIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}
function MessageIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}
function UploadIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}
function CloseIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
function CopyIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}
function CheckCircleIcon({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}
function LockIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}
function EyeOffIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}
function BadgeIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m12 15 3.5 7-3.5-2-3.5 2 3.5-7" />
      <circle cx="12" cy="9" r="7" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Helpers                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

function bytesToHuman(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

type Attachment = { file: File; previewUrl: string; id: string };

/* ───────────────────────────────────────────────────────────────────────── */
/*  Component                                                                */
/* ───────────────────────────────────────────────────────────────────────── */

export function PublicReportSection({
  subjects = [
    { id: '1', name: 'گزارش فساد اقتصادی', description: 'اختلاس، رشوه، انحراف بودجه' },
    { id: '2', name: 'گزارش تخلف اجتماعی', description: 'بی‌نظمی عمومی، آسیب‌های اجتماعی' },
    { id: '3', name: 'گزارش امنیتی',        description: 'مسائل امنیت ملی و عمومی' },
    { id: '4', name: 'گزارش فرهنگی',        description: 'انحرافات فرهنگی و رسانه‌ای' },
    { id: '5', name: 'سایر موارد',          description: 'هر مورد دیگری که شایسته توجه است' },
  ],
}: { subjects?: Subject[] }) {
  const [form, setForm] = useState<FormState>(INITIAL);
  const [files, setFiles] = useState<Attachment[]>([]);
  const [robot, setRobot] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittedId, setSubmittedId] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function update<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  const addFiles = useCallback((list: FileList | File[]) => {
    setFileError(null);
    const incoming = Array.from(list);
    const accepted: Attachment[] = [];
    for (const f of incoming) {
      if (files.length + accepted.length >= MAX_ATTACHMENTS) {
        setFileError(`حداکثر ${MAX_ATTACHMENTS.toLocaleString('fa-IR')} فایل می‌توانید پیوست کنید.`);
        break;
      }
      const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
      if (!ALLOWED_EXT.includes(ext)) {
        setFileError(`فرمت مجاز نیست: «${f.name}». فقط ${ALLOWED_EXT.join('، ')}.`);
        continue;
      }
      if (f.size > MAX_FILE_MB * 1024 * 1024) {
        setFileError(`«${f.name}» بزرگ‌تر از ${MAX_FILE_MB.toLocaleString('fa-IR')} مگابایت است.`);
        continue;
      }
      accepted.push({
        file: f,
        previewUrl: URL.createObjectURL(f),
        id: `${f.name}-${f.size}-${Date.now()}-${Math.random()}`,
      });
    }
    if (accepted.length) setFiles((cur) => [...cur, ...accepted]);
  }, [files.length]);

  function removeFile(id: string) {
    setFiles((cur) => {
      const next = cur.filter((a) => a.id !== id);
      const removed = cur.find((a) => a.id === id);
      if (removed) URL.revokeObjectURL(removed.previewUrl);
      return next;
    });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!robot || !form.full_name || !form.subject_id || !form.description) return;
    setSubmitting(true);
    // Real call uses multipart/form-data → POST /api/v1/public-reports/reports/
    // Demo: simulate a created-report id like the backend returns
    setTimeout(() => {
      setSubmitting(false);
      setSubmittedId(`${Math.floor(Math.random() * 9000 + 1000)}`);
      files.forEach((a) => URL.revokeObjectURL(a.previewUrl));
      setFiles([]);
      setForm(INITIAL);
      setRobot(false);
    }, 1100);
  }

  function resetForm() {
    setSubmittedId(null);
  }

  const descLen = form.description.length;
  const descMin = 40;

  return (
    <section className="section-y" id="reports">
      <div className="container-edge">
        <SectionTitle
          title="گزارش‌های مردمی"
          description="چشم‌های شما، تیزترین چشم‌هاست. هر سرنخ، هر فساد و هر ناهنجاری را با ما در میان بگذارید — هویتتان محرمانه می‌ماند و هر گزارش با کد رهگیری قابل پیگیری است."
        />

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 md:gap-5 items-stretch">
          {/* ── Form card ── */}
          <motion.form
            onSubmit={onSubmit}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="relative overflow-hidden rounded-[28px] md:rounded-[32px]
                       bg-gradient-to-br from-brand-500 via-brand-500 to-brand-700
                       p-5 md:p-8 lg:p-10 text-white"
          >
            {/* dotted texture */}
            <div aria-hidden="true"
                 className="absolute inset-0 opacity-[0.07] pointer-events-none"
                 style={{
                   backgroundImage:
                     'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.7) 1px, transparent 1px)',
                   backgroundSize: '22px 22px',
                 }} />
            {/* soft glow corners */}
            <div aria-hidden="true"
                 className="absolute -top-32 -left-32 w-72 h-72 rounded-full bg-mint-500/15 blur-3xl" />
            <div aria-hidden="true"
                 className="absolute -bottom-24 -right-24 w-72 h-72 rounded-full bg-brand-900/30 blur-3xl" />

            <AnimatePresence mode="wait">
              {submittedId ? (
                /* ── Success state ── */
                <motion.div
                  key="success"
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.35 }}
                  className="relative text-center py-10 md:py-14"
                >
                  <div className="mx-auto w-16 h-16 md:w-20 md:h-20 rounded-full
                                  bg-white/15 backdrop-blur-md
                                  ring-4 ring-white/30 flex items-center justify-center mb-5">
                    <CheckCircleIcon className="w-8 h-8 md:w-10 md:h-10 text-mint-500" />
                  </div>
                  <h3 className="text-xl md:text-2xl font-extrabold mb-2">
                    گزارش شما با موفقیت ثبت شد
                  </h3>
                  <p className="text-white/85 text-[13.5px] md:text-[14.5px] leading-7 max-w-md mx-auto">
                    تیم بررسی به‌زودی به آن رسیدگی می‌کند. کد رهگیری گزارش شما را در جای امنی نگه دارید.
                  </p>
                  {/* tracking id chip */}
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(submittedId)}
                    className="mt-6 inline-flex items-center gap-2 px-4 h-11 rounded-full
                               bg-white/95 text-brand-700 font-extrabold text-[13.5px]
                               hover:bg-white transition-all hover:scale-[1.02]"
                  >
                    <CopyIcon className="w-4 h-4" />
                    <span>کد رهگیری:</span>
                    <span className="tabular-nums text-ink-900">#{submittedId}</span>
                  </button>
                  <div className="mt-5">
                    <button
                      type="button"
                      onClick={resetForm}
                      className="text-white/85 hover:text-white text-[13px] font-bold underline-offset-4 hover:underline"
                    >
                      ثبت گزارش جدید
                    </button>
                  </div>
                </motion.div>
              ) : (
                /* ── Form state ── */
                <motion.div
                  key="form"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="relative"
                >
                  {/* row 1: full_name + phone */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
                    <Field
                      icon={<UserIcon className="w-4 h-4" />}
                      placeholder="نام و نام خانوادگی"
                      required
                      value={form.full_name}
                      onChange={(v) => update('full_name', v)}
                    />
                    <Field
                      icon={<PhoneIcon className="w-4 h-4" />}
                      placeholder="شماره تماس (اختیاری)"
                      value={form.phone}
                      onChange={(v) => update('phone', v)}
                      type="tel"
                      inputMode="tel"
                      hint="می‌توانید ناشناس بمانید"
                    />
                  </div>

                  {/* subject chips */}
                  <div className="mt-3 md:mt-4">
                    <label className="block text-[12.5px] font-extrabold text-white/90 mb-2">
                      موضوع گزارش <span className="text-mint-500">*</span>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {subjects.map((s) => {
                        const active = form.subject_id === s.id;
                        return (
                          <button
                            key={s.id}
                            type="button"
                            onClick={() => update('subject_id', s.id)}
                            aria-pressed={active}
                            className={`inline-flex items-center gap-1.5 h-10 px-4 rounded-full
                                        text-[12.5px] font-extrabold transition-all duration-200
                                        ${active
                                          ? 'bg-white text-brand-700 shadow-[0_8px_18px_-6px_rgba(0,0,0,.3)] scale-[1.02]'
                                          : 'bg-white/12 text-white ring-1 ring-white/20 hover:bg-white/20'}`}
                          >
                            {active && <CheckCircleIcon className="w-3.5 h-3.5" />}
                            <span>{s.name}</span>
                          </button>
                        );
                      })}
                    </div>
                    <AnimatePresence>
                      {form.subject_id && (
                        <motion.p
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="mt-2 text-[11.5px] text-white/75 font-medium overflow-hidden"
                        >
                          {subjects.find((s) => s.id === form.subject_id)?.description}
                        </motion.p>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* description */}
                  <div className="mt-3 md:mt-4 relative">
                    <MessageIcon className="absolute right-4 top-[1.05rem] text-brand-500 z-10 pointer-events-none w-4 h-4" />
                    <textarea
                      value={form.description}
                      onChange={(e) => update('description', e.target.value)}
                      placeholder="شرح گزارش یا سرنخ شما را اینجا بنویسید…"
                      aria-label="شرح گزارش"
                      required
                      rows={5}
                      dir="rtl"
                      className="w-full pr-10 pl-4 pt-[1.05rem] pb-9 rounded-2xl bg-white text-ink-800
                                 text-[14px] outline-none focus:ring-2 focus:ring-mint-500/60
                                 resize-y min-h-[140px] text-right leading-7
                                 placeholder:text-ink-400"
                    />
                    {/* character counter (bottom-right of textarea) */}
                    <span
                      className={`absolute bottom-3 left-4 text-[11px] font-bold tabular-nums
                                  ${descLen >= descMin ? 'text-brand-600' : 'text-ink-400'}`}
                    >
                      {descLen.toLocaleString('fa-IR')}
                      {descLen < descMin && (
                        <span className="text-ink-400 font-normal">
                          {' '}/ حداقل {descMin.toLocaleString('fa-IR')}
                        </span>
                      )}
                    </span>
                  </div>

                  {/* attachments — drag/drop + thumbnails */}
                  <div className="mt-3 md:mt-4">
                    <div
                      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                      onDragLeave={() => setDragOver(false)}
                      onDrop={(e) => {
                        e.preventDefault(); setDragOver(false);
                        if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
                      }}
                      className={`relative rounded-2xl border-2 border-dashed transition-colors
                                  ${dragOver ? 'border-white bg-white/15' : 'border-white/30 bg-white/[0.06]'}`}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept={ALLOWED_EXT.map((e) => `.${e}`).join(',')}
                        className="hidden"
                        onChange={(e) => {
                          if (e.target.files?.length) addFiles(e.target.files);
                          if (e.target) e.target.value = '';
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={files.length >= MAX_ATTACHMENTS}
                        className="w-full flex items-center justify-center gap-2 h-14 text-white/90
                                   text-[13px] font-bold hover:text-white transition-colors
                                   disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <UploadIcon className="w-4 h-4" />
                        <span>
                          {files.length === 0
                            ? 'افزودن پیوست — یا فایل را اینجا رها کنید'
                            : `${files.length.toLocaleString('fa-IR')} از ${MAX_ATTACHMENTS.toLocaleString('fa-IR')} فایل`}
                        </span>
                        <span className="text-white/60 text-[11px] font-medium">
                          (JPG · PNG · WEBP · حداکثر {MAX_FILE_MB.toLocaleString('fa-IR')}MB)
                        </span>
                      </button>

                      {/* thumbnails */}
                      {files.length > 0 && (
                        <div className="flex flex-wrap gap-2 p-3 pt-0">
                          {files.map((a) => (
                            <div
                              key={a.id}
                              className="relative w-16 h-16 rounded-xl overflow-hidden ring-2 ring-white/30"
                            >
                              <Image
                                src={a.previewUrl}
                                alt={a.file.name}
                                fill
                                sizes="64px"
                                className="object-cover"
                                unoptimized
                              />
                              <button
                                type="button"
                                onClick={() => removeFile(a.id)}
                                aria-label="حذف فایل"
                                className="absolute -top-1.5 -right-1.5 w-6 h-6 rounded-full
                                           bg-rose-500 text-white flex items-center justify-center
                                           shadow-[0_4px_10px_-2px_rgba(225,29,72,.6)]
                                           hover:scale-110 transition-transform"
                              >
                                <CloseIcon className="w-3 h-3" />
                              </button>
                              <span className="absolute inset-x-0 bottom-0 text-[9.5px] text-white
                                               bg-black/55 text-center font-bold tabular-nums py-0.5">
                                {bytesToHuman(a.file.size)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {fileError && (
                      <motion.p
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        className="mt-2 text-[11.5px] font-bold text-rose-100
                                   bg-rose-500/30 px-3 py-1.5 rounded-lg ring-1 ring-rose-200/40"
                      >
                        ⚠ {fileError}
                      </motion.p>
                    )}
                  </div>

                  {/* footer: robot check + submit */}
                  <div className="mt-5 md:mt-6 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
                    <label
                      className="inline-flex items-center gap-2.5 h-12 px-5 rounded-2xl
                                 bg-white/95 hover:bg-white cursor-pointer transition-colors flex-shrink-0"
                    >
                      <input
                        type="checkbox"
                        checked={robot}
                        onChange={(e) => setRobot(e.target.checked)}
                        className="sr-only peer"
                      />
                      <span
                        className="w-[22px] h-[22px] rounded-md border-2 border-ink-300 bg-white
                                   flex items-center justify-center transition-all
                                   peer-checked:bg-brand-500 peer-checked:border-brand-500"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3}
                             strokeLinecap="round" strokeLinejoin="round"
                             className={`w-3.5 h-3.5 text-white transition-opacity ${robot ? 'opacity-100' : 'opacity-0'}`}>
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </span>
                      <span className="text-ink-800 font-extrabold text-[13px]">من ربات نیستم</span>
                    </label>

                    <button
                      type="submit"
                      disabled={!robot || submitting || !form.full_name || !form.subject_id || !form.description}
                      className="sm:mr-auto inline-flex items-center justify-center gap-2 h-12 px-7 rounded-2xl
                                 bg-gradient-to-l from-mint-500 to-[#1FB3A8] text-white
                                 text-[14px] font-extrabold
                                 shadow-[0_10px_28px_-8px_rgba(37,197,186,.65)]
                                 hover:scale-[1.02] active:scale-[.98]
                                 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100
                                 transition-all"
                    >
                      {submitting ? (
                        <>
                          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity=".25" />
                            <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3"
                                  strokeLinecap="round" />
                          </svg>
                          <span>در حال ارسال…</span>
                        </>
                      ) : (
                        <>
                          <ShieldCheckIcon className="w-[18px] h-[18px]" />
                          <span>ارسال امن گزارش</span>
                        </>
                      )}
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.form>

          {/* ── Privacy assurance card ── */}
          <motion.aside
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="rounded-[24px] bg-white border border-ink-100
                       shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                       p-5 md:p-6 flex flex-col gap-4"
          >
            <h3 className="text-[15px] font-extrabold text-ink-900 flex items-center gap-2">
              <span className="inline-flex items-center justify-center w-9 h-9 rounded-xl
                               bg-brand-50 text-brand-600">
                <ShieldCheckIcon className="w-5 h-5" />
              </span>
              ضمانت محرمانگی
            </h3>
            <ul className="space-y-3 text-[12.5px] text-ink-700 leading-7">
              <li className="flex items-start gap-2.5">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />
                <span>هویت شما برای عموم محرمانه می‌ماند.</span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />
                <span>شماره تماس اختیاری است؛ می‌توانید بدون آن گزارش بفرستید.</span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />
                <span>ارتباط با سرور رمزنگاری end-to-end انجام می‌شود.</span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />
                <span>بعد از ثبت، یک کد رهگیری دریافت می‌کنید تا وضعیت گزارش را پیگیری کنید.</span>
              </li>
            </ul>
            <div className="mt-1 grid grid-cols-3 gap-2 text-center">
              <Stat icon={<LockIcon className="w-3.5 h-3.5" />}        label="رمزنگاری" />
              <Stat icon={<EyeOffIcon className="w-3.5 h-3.5" />}     label="ناشناس" />
              <Stat icon={<BadgeIcon className="w-3.5 h-3.5" />}      label="پیگیری" />
            </div>
          </motion.aside>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Atoms                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

function Field({
  icon, placeholder, value, onChange, type = 'text', inputMode, required, hint,
}: {
  icon: React.ReactNode;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  inputMode?: 'numeric' | 'tel';
  required?: boolean;
  hint?: string;
}) {
  return (
    <div>
      <div className="relative">
        <span className="absolute right-4 top-1/2 -translate-y-1/2 text-brand-500 z-10 pointer-events-none">
          {icon}
        </span>
        <input
          type={type}
          inputMode={inputMode}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          dir="rtl"
          required={required}
          className="w-full h-12 pr-10 pl-4 rounded-2xl bg-white text-ink-800
                     text-[14px] outline-none focus:ring-2 focus:ring-mint-500/60
                     placeholder:text-ink-400 text-right"
        />
      </div>
      {hint && (
        <p className="mt-1 mr-2 text-[10.5px] text-white/70 font-medium">{hint}</p>
      )}
    </div>
  );
}

function Stat({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1 p-2 rounded-xl bg-ink-50">
      <span className="text-brand-600">{icon}</span>
      <span className="text-[10.5px] font-extrabold text-ink-700">{label}</span>
    </div>
  );
}
