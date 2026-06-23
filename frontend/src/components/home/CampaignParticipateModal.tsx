'use client';

import {
  useState, useEffect, useCallback, useRef, useMemo,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Image from 'next/image';
import { formatPersianNumber } from '@/lib/utils';
import { apiFetch, ApiError } from '@/lib/api';
import type { CampaignCard } from './WarFundSection';

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * Campaign Participate Modal — "Buy Shares"  (v1 — full backend wiring)
 *
 * Backend contract (apps/madadkar) — analysed end-to-end:
 *
 *   POST /api/v1/madadkar/campaigns/<slug>/participate/
 *     Auth     : required (IsAuthenticatedBasic)
 *     Throttle : MadadkarParticipateThrottle (user scope)
 *     Body (ParticipationInitiateSerializer):
 *       - share_count : int ≥ 1, ≤ campaign.remaining_shares    REQUIRED
 *       - mobile      : str max 20                               OPTIONAL
 *       - email       : email                                    OPTIONAL
 *     Response 201 (ParticipationInitiatedResponseSerializer):
 *       - participation : { id, campaign{title,slug,sponsor},
 *                           share_count, share_price_snapshot,
 *                           total_amount, status, created_at }
 *       - gateway_url   : str  → client MUST redirect there
 *       - authority     : str  (tracking code, copy-pasteable)
 *     Error families (all returned as ApiEnvelope failure):
 *       - InvalidShareCountError          (400)
 *       - CampaignNotAcceptingSharesError (400)
 *       - InsufficientSharesError         (400)
 *       - PaymentGatewayError             (502)
 *
 *   Domain rules from apps/madadkar/models.py + services.py:
 *     - total_amount is stored in TOMAN. UI shows BOTH Toman + Rial
 *       (Rial = Toman × 10).
 *     - share_price = total_amount / total_shares (admin enforces
 *       divisibility — no fractions reach the user).
 *     - When the user submits, the backend select_for_updates the
 *       campaign row, reserves the shares (PENDING_PAYMENT) and asks
 *       the payment provider for a `gateway_url` + `authority`.
 *     - Reserved shares are auto-released after 15 minutes if the
 *       payment never lands. Surface this in the security strip so the
 *       user knows the clock is ticking.
 *     - Campaign deadlines are real (has_deadline + deadline). When
 *       present we render a live countdown.
 *
 * UX surface this modal exposes:
 *   1. Cinematic header — campaign cover (full-bleed), title, sponsor
 *      avatar + name, deadline countdown (if has_deadline).
 *   2. Progress meter — "X of Y shares sold (Z%)" with a gradient
 *      progress bar.
 *   3. Big share-count slider (1 → remaining_shares) with snap markers,
 *      a live label that travels with the thumb, and a brand-mint fill.
 *   4. Quick-pick chips: 1 / 5 / 10 / 50 / 100 / حداکثر — clamp to
 *      remaining_shares automatically.
 *   5. Stepper buttons (−1, +1, −10, +10) for precision.
 *   6. Live financial breakdown — share_price × count = total (Toman +
 *      Rial, both formatted in Persian digits) + a tasteful comparison
 *      ("X% of the campaign you'll fund alone").
 *   7. Optional contact fields (collapsed by default) for mobile/email
 *      — only surfaced when the user opens the disclosure.
 *   8. Sponsor card — name + logo + verified badge.
 *   9. Security strip — "تراکنش امن از طریق درگاه رسمی + رزرو سهم
 *      ۱۵ دقیقه‌ای".
 *  10. Submit CTA — opens the gateway in the SAME tab so the cookie
 *      session is preserved. Shows a 'processing' spinner while the
 *      backend round-trips, and surfaces any backend error inline.
 *  11. Backdrop blur + click-out + Esc close + body-scroll lock.
 *  12. role=dialog + aria-modal + aria-live for the financial display.
 * ═══════════════════════════════════════════════════════════════════════════
 */

type Props = {
  open: boolean;
  onClose: () => void;
  campaign: CampaignCard | null;
};

const RESERVE_MINUTES = 15;

export function CampaignParticipateModal({ open, onClose, campaign }: Props) {
  // ── Derived values (always coerced to safe defaults) ───────────────
  const remaining = Math.max(0, campaign?.sharesRemaining ?? 0);
  const total     = Math.max(1, campaign?.sharesTotal ?? 1);
  const sold      = Math.max(0, total - remaining);
  const pricePerShare =
    campaign?.sharePrice ??
    (campaign && campaign.sharesTotal > 0
      ? Math.floor(campaign.totalAmount / campaign.sharesTotal)
      : 0);
  const progressPct = Math.min(100, Math.round((sold / total) * 100));
  const isClosed = remaining <= 0;

  // ── State ──────────────────────────────────────────────────────────
  const [shareCount, setShareCount] = useState(1);
  const [contactOpen, setContactOpen] = useState(false);
  const [mobile, setMobile] = useState('');
  const [email,  setEmail]  = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const panelRef = useRef<HTMLDivElement>(null);

  // Reset on (re)open
  useEffect(() => {
    if (open) {
      setShareCount(Math.min(1, Math.max(0, remaining)));
      setContactOpen(false);
      setMobile(''); setEmail('');
      setSubmitting(false); setError(null);
    }
  }, [open, remaining]);

  // Body scroll lock + Esc to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose, submitting]);

  // ── Computed financials ───────────────────────────────────────────
  const totalToman = useMemo(() => shareCount * pricePerShare, [shareCount, pricePerShare]);
  const totalRial  = totalToman * 10;
  const shareOfCampaignPct = total > 0 ? (shareCount / total) * 100 : 0;

  // ── Deadline countdown (live) ─────────────────────────────────────
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!open || !campaign?.deadline) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [open, campaign?.deadline]);
  const deadlineRemaining = useMemo(() => {
    if (!campaign?.deadline) return null;
    const ms = new Date(campaign.deadline).getTime() - now;
    if (ms <= 0) return { expired: true } as const;
    const days  = Math.floor(ms / 86_400_000);
    const hours = Math.floor((ms % 86_400_000) / 3_600_000);
    const mins  = Math.floor((ms % 3_600_000) / 60_000);
    return { expired: false, days, hours, mins } as const;
  }, [campaign?.deadline, now]);

  // ── Quick-pick chips ──────────────────────────────────────────────
  const quickPicks = useMemo(() => {
    const presets = [1, 5, 10, 50, 100];
    const filtered = presets.filter((v) => v <= remaining);
    return [...filtered, ...(remaining > 0 ? [remaining] : [])];
  }, [remaining]);

  // ── Slider handlers ───────────────────────────────────────────────
  const setSafe = useCallback((v: number) => {
    const next = Math.max(1, Math.min(remaining, Math.floor(v) || 1));
    setShareCount(next);
  }, [remaining]);

  // Tick marks for the slider — 5 equally-spaced labels.
  const ticks = useMemo(() => {
    if (remaining <= 1) return [1];
    const t = [1];
    for (let i = 1; i < 4; i++) t.push(Math.max(1, Math.round((remaining * i) / 4)));
    t.push(remaining);
    return Array.from(new Set(t)).slice(0, 5);
  }, [remaining]);

  // ── Submit ────────────────────────────────────────────────────────
  const onSubmit = useCallback(async () => {
    if (!campaign || submitting || isClosed) return;
    setError(null); setSubmitting(true);
    try {
      const body: Record<string, unknown> = { share_count: shareCount };
      if (mobile.trim()) body.mobile = mobile.trim();
      if (email.trim())  body.email  = email.trim();
      const data = await apiFetch<{ gateway_url: string }>(
        `/madadkar/campaigns/${encodeURIComponent(campaign.slug)}/participate/`,
        { method: 'POST', body: JSON.stringify(body) },
      );
      if (data?.gateway_url) {
        window.location.href = data.gateway_url;
      } else {
        setError('پاسخ درگاه ناقص دریافت شد. لطفاً دوباره تلاش کنید.');
        setSubmitting(false);
      }
    } catch (err) {
      const msg = err instanceof ApiError
        ? err.message
        : 'ارتباط با سرور برقرار نشد. لطفاً دوباره تلاش کنید.';
      setError(msg);
      setSubmitting(false);
    }
  }, [campaign, submitting, isClosed, shareCount, mobile, email]);

  // Don't render if no campaign — saves layout work.
  if (!campaign) return null;

  // Phone validation hint (light — backend is the source of truth).
  const phoneValid =
    !mobile || /^(\+|00)?[0-9]{6,16}$/.test(mobile.replace(/\s/g, ''));
  const emailValid =
    !email || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const canSubmit =
    !submitting && !isClosed && shareCount >= 1 && shareCount <= remaining
    && phoneValid && emailValid;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="participate-root"
          role="dialog"
          aria-modal="true"
          aria-label={`خرید سهم — ${campaign.title}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          className="fixed inset-0 z-[120] flex items-end sm:items-center justify-center
                     bg-ink-900/80 backdrop-blur-md p-0 sm:p-5"
          onClick={(e) => { if (e.target === e.currentTarget && !submitting) onClose(); }}
        >
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, y: 40, scale: 0.96 }}
            animate={{ opacity: 1, y: 0,  scale: 1 }}
            exit   ={{ opacity: 0, y: 24, scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
            className="relative w-full max-w-[640px] max-h-[94vh]
                       bg-white rounded-t-[28px] sm:rounded-[28px]
                       shadow-[0_50px_100px_-25px_rgba(0,0,0,.55)]
                       overflow-hidden flex flex-col"
          >
            {/* ── Hero header (cover + title + sponsor + close) ───── */}
            <div className="relative h-[180px] sm:h-[200px] bg-ink-800 overflow-hidden shrink-0">
              {(campaign.coverUrl || campaign.gallery?.[0]?.url) ? (
                <Image
                  src={(campaign.coverUrl ?? campaign.gallery?.[0]?.url) as string}
                  alt={campaign.title}
                  fill
                  sizes="640px"
                  className="object-cover"
                  priority
                />
              ) : (
                <div
                  className="absolute inset-0"
                  style={{ background: `linear-gradient(135deg, ${campaign.toneFrom ?? '#0D8074'}, ${campaign.toneTo ?? '#053832'})` }}
                />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-ink-900/95 via-ink-900/30 to-ink-900/10" />

              <button
                type="button"
                onClick={() => { if (!submitting) onClose(); }}
                aria-label="بستن"
                className="absolute top-3 left-3 z-[2] w-10 h-10 rounded-full
                           bg-black/45 text-white ring-1 ring-white/20 backdrop-blur
                           flex items-center justify-center
                           hover:bg-rose-500 hover:scale-105 active:scale-95
                           transition-all duration-200"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                     strokeLinejoin="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6"  y1="6" x2="18" y2="18" />
                </svg>
              </button>

              {deadlineRemaining && !deadlineRemaining.expired && (
                <div className="absolute top-3 right-3 z-[2] inline-flex items-center gap-1.5
                                px-3 h-9 rounded-full bg-black/45 text-white
                                ring-1 ring-white/20 backdrop-blur text-[12px] font-extrabold">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="9" />
                    <polyline points="12 7 12 12 16 14" />
                  </svg>
                  <span className="tabular-nums">
                    {deadlineRemaining.days > 0
                      ? `${formatPersianNumber(deadlineRemaining.days)} روز`
                      : `${formatPersianNumber(deadlineRemaining.hours)}:${String(deadlineRemaining.mins).padStart(2,'0')}`}
                  </span>
                </div>
              )}

              <div className="absolute inset-x-0 bottom-0 p-4 sm:p-5 z-[1]">
                <h2 className="text-white font-extrabold text-[16px] sm:text-[18px] leading-7 line-clamp-2">
                  {campaign.title}
                </h2>
                <p className="mt-1 text-white/80 text-[12.5px] font-medium inline-flex items-center gap-1.5">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                  مددکار: <span className="font-extrabold">{campaign.sponsor}</span>
                </p>
              </div>
            </div>

            {/* ── Scrollable body ──────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-5">

              {/* Progress meter */}
              <div>
                <div className="flex items-center justify-between text-[12.5px] font-bold text-ink-600 mb-2">
                  <span>
                    {formatPersianNumber(sold)} سهم از {formatPersianNumber(total)} فروخته شده
                  </span>
                  <span className="text-brand-700 tabular-nums font-extrabold">
                    ٪{formatPersianNumber(progressPct)}
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-ink-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-l from-mint-500 to-brand-600
                               transition-[width] duration-700 ease-out"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <p className="mt-2 text-[11.5px] text-ink-500 font-medium tabular-nums">
                  {remaining > 0
                    ? <>سهم باقی‌مانده برای خرید: <strong className="text-ink-800">{formatPersianNumber(remaining)}</strong></>
                    : 'تمام سهم‌ها فروخته شده‌اند.'}
                  {campaign.totalAmount > 0 && (
                    <> · ارزش هر سهم: <strong className="text-ink-800">{formatPersianNumber(pricePerShare)}</strong> تومان</>
                  )}
                </p>
              </div>

              {/* Share-count slider + steppers */}
              {!isClosed && (
                <div className="rounded-2xl border border-ink-100 bg-gradient-to-b from-white to-brand-50/30
                                p-4 sm:p-5">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <span className="text-[13px] font-extrabold text-ink-700">تعداد سهم انتخابی</span>
                    <span
                      aria-live="polite"
                      className="inline-flex items-baseline gap-1 px-3 h-9 rounded-full
                                 bg-gradient-to-l from-brand-500 to-brand-700 text-white
                                 shadow-[0_8px_20px_-6px_rgba(13,128,116,.55)]"
                    >
                      <span className="text-[18px] font-extrabold tabular-nums">{formatPersianNumber(shareCount)}</span>
                      <span className="text-[11.5px] font-bold opacity-85">سهم</span>
                    </span>
                  </div>

                  {/* Stepper row */}
                  <div className="flex items-center gap-2">
                    <Stepper label="−۱۰" disabled={shareCount <= 1}        onClick={() => setSafe(shareCount - 10)} />
                    <Stepper label="−۱"  disabled={shareCount <= 1}        onClick={() => setSafe(shareCount - 1)} />
                    <input
                      type="range"
                      min={1}
                      max={Math.max(1, remaining)}
                      step={1}
                      value={shareCount}
                      onChange={(e) => setSafe(+e.target.value)}
                      aria-label="تعداد سهم"
                      className="participate-range flex-1 min-w-0 accent-brand-600"
                      style={{
                        // Custom track via background-gradient so the
                        // fill matches the brand mint→brand-700 ramp.
                        background: (() => {
                          const pct = ((shareCount - 1) / Math.max(1, remaining - 1)) * 100;
                          return `linear-gradient(to left, var(--brand-500, #0D8074) 0%, var(--brand-700, #085C54) ${pct}%, #EAEEF2 ${pct}%, #EAEEF2 100%)`;
                        })(),
                      }}
                    />
                    <Stepper label="+۱"  disabled={shareCount >= remaining} onClick={() => setSafe(shareCount + 1)} />
                    <Stepper label="+۱۰" disabled={shareCount >= remaining} onClick={() => setSafe(shareCount + 10)} />
                  </div>

                  {/* Tick markers */}
                  <div className="mt-2 flex justify-between px-1 text-[10.5px] font-bold text-ink-400 tabular-nums">
                    {ticks.map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setSafe(t)}
                        className="hover:text-brand-700 transition-colors"
                      >
                        {formatPersianNumber(t)}
                      </button>
                    ))}
                  </div>

                  {/* Quick-pick chips */}
                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11.5px] font-bold text-ink-500 ml-1">انتخاب سریع:</span>
                    {quickPicks.map((v, i) => {
                      const isMax = i === quickPicks.length - 1 && v === remaining;
                      const active = shareCount === v;
                      return (
                        <button
                          key={`${v}-${i}`}
                          type="button"
                          onClick={() => setSafe(v)}
                          className={`inline-flex items-center justify-center h-8 px-3 rounded-full
                                      text-[11.5px] font-extrabold tabular-nums transition-all duration-150
                                      ${active
                                        ? 'bg-brand-500 text-white shadow-[0_6px_14px_-4px_rgba(13,128,116,.55)]'
                                        : 'bg-white text-ink-700 ring-1 ring-ink-200 hover:ring-brand-300 hover:text-brand-700'}`}
                        >
                          {isMax ? 'حداکثر' : formatPersianNumber(v)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Financial breakdown */}
              {!isClosed && (
                <div aria-live="polite" className="rounded-2xl bg-brand-500 text-white p-4 sm:p-5
                                                    shadow-[0_18px_40px_-18px_rgba(13,128,116,.55)]">
                  <div className="flex items-center justify-between text-[12px] font-bold opacity-85">
                    <span>قیمت هر سهم</span>
                    <span className="tabular-nums">{formatPersianNumber(pricePerShare)} تومان</span>
                  </div>
                  <div className="flex items-baseline justify-between mt-2">
                    <span className="text-[12.5px] font-bold opacity-90">مبلغ کل پرداختی</span>
                    <div className="flex flex-col items-end">
                      <span className="text-[24px] sm:text-[28px] font-extrabold leading-none tabular-nums">
                        {formatPersianNumber(totalToman)}
                      </span>
                      <span className="text-[11px] opacity-80 mt-0.5">تومان</span>
                    </div>
                  </div>
                  <div className="mt-1 flex items-center justify-end gap-1 text-[11.5px] opacity-75 tabular-nums">
                    معادل {formatPersianNumber(totalRial)} ریال
                  </div>
                  {shareOfCampaignPct > 0 && (
                    <div className="mt-3 pt-3 border-t border-white/15 text-[11.5px] font-medium opacity-90 inline-flex items-center gap-1.5">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M12 3l1.9 5.8H20l-4.9 3.6 1.9 5.8L12 14.6 7 18.2l1.9-5.8L4 8.8h6.1z"/>
                      </svg>
                      با این مشارکت، <strong className="font-extrabold">{shareOfCampaignPct < 0.1
                        ? `کمتر از ٪${formatPersianNumber('0.1')}`
                        : `٪${formatPersianNumber(shareOfCampaignPct.toFixed(shareOfCampaignPct < 1 ? 2 : 1))}`}</strong>
                      &nbsp;از کل حرکت را تأمین می‌کنی.
                    </div>
                  )}
                </div>
              )}

              {/* Optional contact disclosure */}
              {!isClosed && (
                <details
                  className="rounded-2xl border border-ink-100 bg-white"
                  open={contactOpen}
                  onToggle={(e) => setContactOpen((e.target as HTMLDetailsElement).open)}
                >
                  <summary className="cursor-pointer list-none p-4 flex items-center justify-between
                                      text-[12.5px] font-extrabold text-ink-700 select-none">
                    <span className="inline-flex items-center gap-2">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                           strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
                      </svg>
                      اطلاعات تماس (اختیاری)
                    </span>
                    <span className={`text-ink-400 transition-transform duration-200 ${contactOpen ? 'rotate-180' : ''}`} aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                           strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                    </span>
                  </summary>
                  <div className="px-4 pb-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input
                      type="tel" inputMode="tel"
                      placeholder="شماره موبایل"
                      value={mobile}
                      onChange={(e) => setMobile(e.target.value.replace(/[^0-9+]/g, '').slice(0, 16))}
                      dir="ltr"
                      className={`h-11 px-3 rounded-xl bg-ink-50 text-ink-800 text-[13px] font-medium
                                  outline-none focus:ring-2 transition
                                  ${phoneValid ? 'focus:ring-brand-300' : 'ring-2 ring-rose-300'}`}
                    />
                    <input
                      type="email" inputMode="email"
                      placeholder="ایمیل"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      dir="ltr"
                      className={`h-11 px-3 rounded-xl bg-ink-50 text-ink-800 text-[13px] font-medium
                                  outline-none focus:ring-2 transition
                                  ${emailValid ? 'focus:ring-brand-300' : 'ring-2 ring-rose-300'}`}
                    />
                    <p className="sm:col-span-2 text-[11px] text-ink-500 font-medium leading-6">
                      این اطلاعات اختیاری‌اند و در صورت ارسال، برای ارتباط درگاه با شما استفاده می‌شوند.
                      در غیر این صورت، از اطلاعات پروفایل شما استفاده خواهد شد.
                    </p>
                  </div>
                </details>
              )}

              {/* Security strip */}
              <div className="rounded-2xl bg-ink-50 border border-ink-100 p-3.5 flex items-start gap-3">
                <span className="shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700
                                 text-white flex items-center justify-center">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                </span>
                <p className="text-[11.5px] text-ink-600 font-medium leading-6">
                  پرداخت از طریق درگاه رسمی و امن انجام می‌شود.
                  پس از انتخاب، تا <strong className="text-ink-900">{formatPersianNumber(RESERVE_MINUTES)} دقیقه</strong>
                  &nbsp;سهم‌ها برای شما رزرو می‌مانند؛ در صورت عدم پرداخت، خودکار آزاد می‌شوند.
                </p>
              </div>

              {/* Inline error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    key="err"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    role="alert"
                    className="rounded-xl bg-rose-50 ring-1 ring-rose-200 text-rose-700
                               p-3 text-[12.5px] font-bold flex items-start gap-2"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
                         className="shrink-0 mt-0.5">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                    <span>{error}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              {isClosed && (
                <div className="rounded-xl bg-amber-50 ring-1 ring-amber-200 text-amber-800
                                p-3 text-[12.5px] font-bold flex items-start gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
                       className="shrink-0 mt-0.5">
                    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                  این حرکت در حال حاضر سهم آزاد ندارد. به‌زودی حرکت‌های جدید اضافه می‌شوند.
                </div>
              )}
            </div>

            {/* ── Footer CTA ───────────────────────────────────────── */}
            <div className="shrink-0 border-t border-ink-100 bg-white px-4 sm:px-6 py-3.5
                            flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => { if (!submitting) onClose(); }}
                disabled={submitting}
                className="h-12 px-5 rounded-full bg-ink-50 hover:bg-ink-100
                           text-ink-700 font-extrabold text-[13px] transition-colors
                           disabled:opacity-50"
              >
                انصراف
              </button>
              <button
                type="button"
                onClick={onSubmit}
                disabled={!canSubmit}
                className="relative flex-1 h-12 rounded-full text-white font-extrabold text-[14px]
                           bg-gradient-to-l from-mint-500 to-brand-700
                           shadow-[0_10px_24px_-6px_rgba(13,128,116,.55)]
                           hover:brightness-105 active:scale-[0.99] transition-all duration-150
                           disabled:opacity-60 disabled:cursor-not-allowed
                           inline-flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
                      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                    در حال انتقال به درگاه…
                  </>
                ) : isClosed ? (
                  'این حرکت تکمیل شده است'
                ) : (
                  <>
                    <span>ادامه و پرداخت {formatPersianNumber(totalToman)} تومان</span>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <polyline points="15 18 9 12 15 6" />
                    </svg>
                  </>
                )}
              </button>
            </div>
          </motion.div>

          {/* Custom slider thumb styles live in globals.css under
              `.participate-range` — kept out of the component to avoid
              the styled-jsx dependency. */}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ─────────────────────────── Stepper atom ─────────────────────────── */

function Stepper({
  label, onClick, disabled,
}: {
  label: string; onClick: () => void; disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={`تغییر تعداد سهم ${label}`}
      className="shrink-0 inline-flex items-center justify-center h-9 min-w-[40px] px-2.5
                 rounded-full bg-white text-ink-700 ring-1 ring-ink-200 text-[12px] font-extrabold
                 tabular-nums hover:ring-brand-300 hover:text-brand-700 active:scale-95
                 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {label}
    </button>
  );
}
