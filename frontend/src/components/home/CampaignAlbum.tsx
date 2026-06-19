'use client';

import {
  useState, useEffect, useCallback, useRef, useMemo,
} from 'react';
import { motion, AnimatePresence, type PanInfo } from 'framer-motion';
import { formatPersianNumber } from '@/lib/utils';

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * Campaign Album — v2 ("Cinema")
 *
 * Backend contract (apps/madadkar):
 *   GET /api/v1/madadkar/campaigns/<slug>/  → CampaignPublicDetailSerializer
 *     {
 *       ...,
 *       cover_image: str,
 *       gallery_images: [
 *         { id, image, alt_text, display_order, created_at }, ...
 *       ]
 *     }
 *
 *   - ALLOWED_IMAGE_EXTENSIONS = {jpg, jpeg, png, webp}
 *   - MAX_IMAGE_SIZE_MB = 5
 *   - There is NO hard cap on the number of gallery_images per campaign —
 *     admins may add as many as they like. Sort order is enforced by the
 *     backend Meta.ordering = ["display_order", "created_at"].
 *   - Cover lives on Campaign.cover_image and is conceptually slot 0
 *     (we prepend it before the sorted gallery_images stream).
 *   - alt_text (max 200) is the caption we surface below the stage.
 *
 * This viewer NEVER calls the API itself — the page-level container is
 * responsible for fetching detail and feeding us a normalized images[].
 *
 * Feature set ("cinema" preset):
 *   1. Cinematic backdrop — a blurred copy of the current image fills
 *      the entire scene (Spotify Now-Playing vibe).
 *   2. Smart preloading — the next + previous image start loading as
 *      soon as the active index changes; opening a new image is instant.
 *   3. Per-image skeleton + fade-in on load.
 *   4. Pinch + wheel + double-tap ZOOM with drag-to-pan; constrained
 *      so the image never disappears from the stage. A floating zoom
 *      HUD (minus / reset / plus) is anchored to the bottom-right.
 *   5. Touch swipe (Framer Motion drag) — natural left/right with RTL
 *      mapping (drag-right → previous, drag-left → next).
 *   6. Keyboard: ←/→ navigate (RTL-mapped), Esc close, Space play/pause
 *      slideshow, F toggle fullscreen, ?/H toggle help overlay,
 *      +/−/0 zoom controls.
 *   7. Slideshow (autoplay) with a top progress bar; pauses on hover
 *      / focus / when zoomed in. 5s per slide.
 *   8. Fullscreen via the Fullscreen API.
 *   9. Action HUD: Open original in new tab, Download, Copy URL,
 *      Slideshow toggle, Fullscreen toggle. All buttons are keyboard
 *      reachable + aria-labelled.
 *  10. Caption strip (alt_text) animates in/out with the slide.
 *  11. Filmstrip — RTL-aware horizontal scroll, active thumb scales up
 *      and gets a brand ring + glow; dot indicator below for small
 *      galleries (≤ 8 images) for ergonomics on big screens.
 *  12. Help overlay listing every shortcut, dismissable with same key.
 *  13. Concentric corners — outer panel r=28, stage r=24, image natural.
 *  14. A11y — role=dialog + aria-modal + focus-trap-light (body scroll
 *      lock), aria-live counter, aria-pressed on every toggle.
 * ═══════════════════════════════════════════════════════════════════════════
 */

export type AlbumImage = {
  url: string;
  alt?: string;
  width?: number;
  height?: number;
};

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  sponsor?: string;
  images: AlbumImage[];
  loading?: boolean;
  startIndex?: number;
};

const SLIDESHOW_INTERVAL_MS = 5_000;

export function CampaignAlbum({
  open, onClose, title, sponsor, images, loading = false, startIndex = 0,
}: Props) {
  // ── Core navigation state ───────────────────────────────────────────
  const [index, setIndex] = useState(startIndex);
  const total = images.length;
  const stripRef = useRef<HTMLDivElement>(null);

  // ── Zoom / pan state ────────────────────────────────────────────────
  const [zoom, setZoom] = useState(1);
  const [pan,  setPan]  = useState({ x: 0, y: 0 });
  const [imgReady, setImgReady] = useState(false);
  const pinchStateRef = useRef<{ startDist: number; startZoom: number } | null>(null);

  // ── Slideshow + help + fullscreen state ─────────────────────────────
  const [slideshow, setSlideshow] = useState(false);
  const [helpOpen,  setHelpOpen]  = useState(false);
  const [isFs,      setIsFs]      = useState(false);
  const [hovering,  setHovering]  = useState(false);
  const [progress,  setProgress]  = useState(0);   // 0..1 for slideshow
  const [copied,    setCopied]    = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const imgRef   = useRef<HTMLImageElement>(null);

  // Reset whenever the album is (re)opened for a new campaign.
  useEffect(() => {
    if (open) {
      setIndex(Math.min(startIndex, Math.max(0, total - 1)));
      setZoom(1); setPan({ x: 0, y: 0 });
      setSlideshow(false); setHelpOpen(false); setProgress(0);
      setImgReady(false); setCopied(false);
    }
  }, [open, startIndex, total]);

  // Reset zoom + pan whenever the active image changes.
  useEffect(() => {
    setZoom(1); setPan({ x: 0, y: 0 }); setImgReady(false);
  }, [index]);

  // ── Smart preloading of neighbours ──────────────────────────────────
  useEffect(() => {
    if (!open || total === 0) return;
    const toPreload = [
      images[(index + 1) % total]?.url,
      images[(index - 1 + total) % total]?.url,
    ].filter(Boolean) as string[];
    toPreload.forEach((src) => {
      const im = new Image();
      im.src = src;
    });
  }, [open, index, total, images]);

  // ── Filmstrip scroll-into-view for the active thumb ─────────────────
  useEffect(() => {
    if (!open) return;
    const el = stripRef.current?.querySelector<HTMLElement>(`[data-thumb="${index}"]`);
    el?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [open, index]);

  const next = useCallback(
    () => setIndex((i) => (total ? (i + 1) % total : 0)),
    [total],
  );
  const prev = useCallback(
    () => setIndex((i) => (total ? (i - 1 + total) % total : 0)),
    [total],
  );
  const goTo = useCallback((i: number) => setIndex(Math.max(0, Math.min(total - 1, i))), [total]);

  // ── Zoom controls ───────────────────────────────────────────────────
  const setSafeZoom = useCallback((nz: number) => {
    const clamped = Math.max(1, Math.min(4, nz));
    setZoom(clamped);
    if (clamped === 1) setPan({ x: 0, y: 0 });
  }, []);
  const zoomIn  = useCallback(() => setSafeZoom(zoom + 0.5), [zoom, setSafeZoom]);
  const zoomOut = useCallback(() => setSafeZoom(zoom - 0.5), [zoom, setSafeZoom]);
  const zoomReset = useCallback(() => setSafeZoom(1), [setSafeZoom]);

  // Constrain pan so the image edges never leave the stage.
  const constrainPan = useCallback((nx: number, ny: number, z = zoom) => {
    const stage = stageRef.current;
    if (!stage || z <= 1) return { x: 0, y: 0 };
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    const maxX = (w * (z - 1)) / 2;
    const maxY = (h * (z - 1)) / 2;
    return {
      x: Math.max(-maxX, Math.min(maxX, nx)),
      y: Math.max(-maxY, Math.min(maxY, ny)),
    };
  }, [zoom]);

  // ── Body scroll lock + keyboard shortcuts ───────────────────────────
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      // Allow Esc to dismiss help first
      if (e.key === 'Escape') {
        if (helpOpen)        setHelpOpen(false);
        else if (zoom > 1)   zoomReset();
        else if (slideshow)  setSlideshow(false);
        else                 onClose();
        return;
      }
      if (e.key === 'ArrowLeft')        next();
      else if (e.key === 'ArrowRight')  prev();
      else if (e.key === ' ')          { e.preventDefault(); setSlideshow((s) => !s); }
      else if (e.key === 'f' || e.key === 'F') toggleFs();
      else if (e.key === '?' || e.key === 'h' || e.key === 'H') setHelpOpen((h) => !h);
      else if (e.key === '+' || e.key === '=')  zoomIn();
      else if (e.key === '-' || e.key === '_')  zoomOut();
      else if (e.key === '0')                   zoomReset();
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, helpOpen, zoom, slideshow, next, prev, onClose, zoomIn, zoomOut, zoomReset]);

  // ── Slideshow tick ──────────────────────────────────────────────────
  useEffect(() => {
    if (!open || !slideshow || total <= 1) { setProgress(0); return; }
    if (hovering || zoom > 1) { setProgress(0); return; }
    let raf = 0;
    let startedAt = performance.now();
    const tick = (t: number) => {
      const elapsed = t - startedAt;
      const p = Math.min(1, elapsed / SLIDESHOW_INTERVAL_MS);
      setProgress(p);
      if (p >= 1) {
        startedAt = t;
        setProgress(0);
        next();
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [open, slideshow, total, hovering, zoom, next]);

  // ── Fullscreen API ──────────────────────────────────────────────────
  const toggleFs = useCallback(async () => {
    const el = panelRef.current;
    if (!el) return;
    try {
      if (!document.fullscreenElement) {
        await el.requestFullscreen?.();
        setIsFs(true);
      } else {
        await document.exitFullscreen?.();
        setIsFs(false);
      }
    } catch { /* user-cancelled */ }
  }, []);
  useEffect(() => {
    const onChange = () => setIsFs(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  // ── Swipe (only when not zoomed) ────────────────────────────────────
  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (zoom > 1) return;     // panning handled by the mouse/touch handlers
    const dx = info.offset.x;
    const vx = info.velocity.x;
    if (dx > 70 || vx > 500)        prev();  // drag-right → previous (RTL)
    else if (dx < -70 || vx < -500) next();  // drag-left  → next     (RTL)
  };

  // ── Mouse pan when zoomed in ────────────────────────────────────────
  const panStartRef = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const onPanPointerDown = (e: React.PointerEvent) => {
    if (zoom <= 1) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    panStartRef.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
  };
  const onPanPointerMove = (e: React.PointerEvent) => {
    const s = panStartRef.current;
    if (!s) return;
    const np = constrainPan(s.px + (e.clientX - s.x), s.py + (e.clientY - s.y));
    setPan(np);
  };
  const onPanPointerUp = () => { panStartRef.current = null; };

  // ── Wheel zoom + pinch ──────────────────────────────────────────────
  const onWheel = (e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey && !e.shiftKey) return;  // require modifier
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.25 : -0.25;
    setSafeZoom(zoom + delta);
  };
  const onTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      pinchStateRef.current = { startDist: Math.hypot(dx, dy), startZoom: zoom };
    }
  };
  const onTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 2 && pinchStateRef.current) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.hypot(dx, dy);
      const ratio = dist / pinchStateRef.current.startDist;
      setSafeZoom(pinchStateRef.current.startZoom * ratio);
    }
  };
  const onTouchEnd = () => { pinchStateRef.current = null; };

  // ── Double-tap / double-click to toggle zoom ────────────────────────
  const handleDoubleClick = () => setSafeZoom(zoom > 1 ? 1 : 2.25);

  // ── Action HUD callbacks ────────────────────────────────────────────
  const current = images[index];
  const onDownload = useCallback(() => {
    if (!current?.url) return;
    const a = document.createElement('a');
    a.href = current.url;
    const name = current.alt?.trim() || `madadkar-${index + 1}`;
    a.download = `${name}.jpg`;
    a.target = '_blank';
    a.rel = 'noopener';
    document.body.appendChild(a); a.click(); a.remove();
  }, [current, index]);
  const onCopyUrl = useCallback(async () => {
    if (!current?.url) return;
    try {
      const abs = new URL(current.url, window.location.origin).href;
      await navigator.clipboard.writeText(abs);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* clipboard might be blocked */ }
  }, [current]);

  // ── Memoized aria text + visible counter ────────────────────────────
  const counter = useMemo(() => {
    if (!total) return '۰';
    return `${formatPersianNumber(index + 1)} / ${formatPersianNumber(total)}`;
  }, [index, total]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="album-root"
          role="dialog"
          aria-modal="true"
          aria-label={`گالری تصاویر — ${title}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          className="fixed inset-0 z-[110] flex items-center justify-center
                     bg-ink-900/85 backdrop-blur-md p-2 sm:p-5"
          onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, scale: 0.94, y: 18 }}
            animate={{ opacity: 1, scale: 1,    y: 0  }}
            exit   ={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
            onMouseEnter={() => setHovering(true)}
            onMouseLeave={() => setHovering(false)}
            className="relative w-full max-w-[1180px] h-[92vh]
                       bg-ink-900 rounded-[28px] overflow-hidden flex flex-col
                       shadow-[0_50px_100px_-25px_rgba(0,0,0,.65)]"
          >
            {/* ─── Slideshow progress bar (top edge) ────────────────── */}
            {slideshow && total > 1 && (
              <div
                aria-hidden="true"
                className="absolute top-0 inset-x-0 h-[3px] z-[6] bg-white/10"
              >
                <div
                  className="h-full bg-gradient-to-l from-mint-500 to-brand-500
                             transition-[width] duration-100 ease-linear"
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
            )}

            {/* ─── Header ───────────────────────────────────────────── */}
            <div className="relative z-[5] flex items-center justify-between gap-3 px-4 md:px-6 py-3.5
                            bg-gradient-to-b from-ink-900/95 to-ink-900/0 text-white">
              <div className="flex items-center gap-3 min-w-0">
                <span className="shrink-0 inline-flex w-10 h-10 rounded-xl
                                 bg-gradient-to-br from-mint-500 to-brand-700
                                 items-center justify-center
                                 shadow-[0_8px_18px_-6px_rgba(13,128,116,.55)]">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="2.1" strokeLinecap="round"
                       strokeLinejoin="round" aria-hidden="true">
                    <rect x="3" y="3" width="18" height="18" rx="3" />
                    <circle cx="9" cy="9" r="2" />
                    <path d="m21 15-5-5L5 21" />
                  </svg>
                </span>
                <div className="min-w-0">
                  <h3 className="text-[14.5px] md:text-[15.5px] font-extrabold leading-6 truncate">
                    {title}
                  </h3>
                  {sponsor && (
                    <p className="text-[12px] text-white/60 font-medium leading-5 truncate">
                      مددکار: {sponsor}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span
                  aria-live="polite"
                  className="hidden sm:inline-flex items-center px-3 h-9 rounded-full
                             bg-white/10 text-white text-[12px] font-extrabold tabular-nums
                             ring-1 ring-white/15 backdrop-blur"
                >
                  {counter}
                </span>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="بستن (Esc)"
                  className="w-10 h-10 rounded-full bg-white/10 text-white
                             hover:bg-rose-500 hover:scale-105 active:scale-95
                             flex items-center justify-center ring-1 ring-white/15
                             backdrop-blur transition-all duration-200"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                       strokeLinejoin="round" aria-hidden="true">
                    <line x1="18" y1="6"  x2="6"  y2="18" />
                    <line x1="6"  y1="6"  x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>

            {/* ─── Stage ───────────────────────────────────────────── */}
            <div
              ref={stageRef}
              className="relative flex-1 overflow-hidden"
              onWheel={onWheel}
              onTouchStart={onTouchStart}
              onTouchMove={onTouchMove}
              onTouchEnd={onTouchEnd}
            >
              {/* Cinematic blurred backdrop */}
              {current?.url && (
                <div
                  aria-hidden="true"
                  className="absolute inset-0 pointer-events-none"
                  style={{
                    backgroundImage: `url("${current.url}")`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                    filter: 'blur(48px) saturate(1.4) brightness(.55)',
                    transform: 'scale(1.12)',
                  }}
                />
              )}
              <div
                aria-hidden="true"
                className="absolute inset-0 pointer-events-none"
                style={{
                  background:
                    'radial-gradient(ellipse at center, rgba(0,0,0,0) 50%, rgba(0,0,0,.55) 100%)',
                }}
              />

              {loading ? (
                <div className="absolute inset-0 flex items-center justify-center text-white/85">
                  <Spinner />
                </div>
              ) : total === 0 ? (
                <div className="absolute inset-0 flex items-center justify-center text-white/80 text-[13px] font-medium">
                  تصویری برای نمایش وجود ندارد.
                </div>
              ) : (
                <>
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, scale: 0.985 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.99 }}
                      transition={{ duration: 0.28 }}
                      drag={zoom > 1 ? false : 'x'}
                      dragConstraints={{ left: 0, right: 0 }}
                      dragElastic={0.16}
                      onDragEnd={onDragEnd}
                      onDoubleClick={handleDoubleClick}
                      onPointerDown={onPanPointerDown}
                      onPointerMove={onPanPointerMove}
                      onPointerUp={onPanPointerUp}
                      onPointerCancel={onPanPointerUp}
                      className="absolute inset-0 select-none flex items-center justify-center"
                      style={{
                        cursor: zoom > 1 ? (panStartRef.current ? 'grabbing' : 'grab') : 'zoom-in',
                        touchAction: zoom > 1 ? 'none' : 'pan-y',
                      }}
                    >
                      {!imgReady && (
                        <div className="absolute inset-0 flex items-center justify-center text-white/70">
                          <Spinner />
                        </div>
                      )}
                      {current?.url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          ref={imgRef}
                          src={current.url}
                          alt={current.alt || title}
                          draggable={false}
                          onLoad={() => setImgReady(true)}
                          className="max-w-[94%] max-h-[88%] object-contain
                                     pointer-events-none
                                     drop-shadow-[0_20px_50px_rgba(0,0,0,.55)]
                                     transition-opacity duration-300"
                          style={{
                            transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom})`,
                            transformOrigin: 'center center',
                            transition: 'transform .25s cubic-bezier(.22,1,.36,1)',
                            opacity: imgReady ? 1 : 0,
                          }}
                        />
                      )}
                    </motion.div>
                  </AnimatePresence>

                  {/* Edge nav buttons */}
                  {total > 1 && (
                    <>
                      <button
                        type="button"
                        onClick={prev}
                        aria-label="تصویر قبلی (→)"
                        className="absolute top-1/2 right-2 sm:right-4 -translate-y-1/2 z-[6]
                                   w-12 h-12 rounded-full bg-white/10 text-white
                                   hover:bg-white hover:text-ink-900 hover:scale-110 active:scale-95
                                   flex items-center justify-center
                                   ring-1 ring-white/20 backdrop-blur-md
                                   shadow-[0_10px_24px_-6px_rgba(0,0,0,.55)]
                                   transition-all duration-200"
                      >
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="9 6 15 12 9 18" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={next}
                        aria-label="تصویر بعدی (←)"
                        className="absolute top-1/2 left-2 sm:left-4 -translate-y-1/2 z-[6]
                                   w-12 h-12 rounded-full bg-white/10 text-white
                                   hover:bg-white hover:text-ink-900 hover:scale-110 active:scale-95
                                   flex items-center justify-center
                                   ring-1 ring-white/20 backdrop-blur-md
                                   shadow-[0_10px_24px_-6px_rgba(0,0,0,.55)]
                                   transition-all duration-200"
                      >
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="15 18 9 12 15 6" />
                        </svg>
                      </button>
                    </>
                  )}

                  {/* Mobile counter */}
                  <span
                    className="sm:hidden absolute top-3 left-1/2 -translate-x-1/2 z-[6]
                               inline-flex items-center px-3 h-7 rounded-full
                               bg-black/60 text-white text-[11.5px] font-extrabold tabular-nums
                               ring-1 ring-white/15 backdrop-blur"
                  >
                    {counter}
                  </span>

                  {/* Caption — alt_text from backend */}
                  {current?.alt && (
                    <div
                      className="absolute bottom-3 inset-x-0 z-[5] flex justify-center px-4 pointer-events-none"
                      aria-hidden="true"
                    >
                      <motion.span
                        key={`cap-${index}`}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.25 }}
                        className="max-w-[88%] text-center px-4 py-2 rounded-full
                                   bg-black/55 text-white text-[12.5px] font-medium
                                   ring-1 ring-white/15 backdrop-blur-md
                                   line-clamp-2 leading-6"
                      >
                        {current.alt}
                      </motion.span>
                    </div>
                  )}

                  {/* Zoom HUD — bottom-right */}
                  <div className="absolute bottom-3 right-3 z-[7] flex items-center gap-1.5
                                  bg-black/55 ring-1 ring-white/15 backdrop-blur
                                  rounded-full px-1.5 py-1.5">
                    <HudButton onClick={zoomOut} ariaLabel="کوچک‌نمایی (−)" disabled={zoom <= 1}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                           stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                           strokeLinejoin="round" aria-hidden="true">
                        <line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                    </HudButton>
                    <button
                      type="button"
                      onClick={zoomReset}
                      aria-label="بازنشانی بزرگ‌نمایی (۰)"
                      className="px-2 h-7 min-w-[44px] rounded-full text-white text-[11px] font-extrabold tabular-nums
                                 hover:bg-white/10 transition-colors"
                    >
                      {`٪${formatPersianNumber(Math.round(zoom * 100))}`}
                    </button>
                    <HudButton onClick={zoomIn} ariaLabel="بزرگ‌نمایی (+)" disabled={zoom >= 4}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                           stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                           strokeLinejoin="round" aria-hidden="true">
                        <line x1="5"  y1="12" x2="19" y2="12" />
                        <line x1="12" y1="5"  x2="12" y2="19" />
                      </svg>
                    </HudButton>
                  </div>

                  {/* Action HUD — bottom-left */}
                  <div className="absolute bottom-3 left-3 z-[7] flex items-center gap-1.5
                                  bg-black/55 ring-1 ring-white/15 backdrop-blur
                                  rounded-full px-1.5 py-1.5">
                    {total > 1 && (
                      <HudButton
                        onClick={() => setSlideshow((s) => !s)}
                        ariaLabel={slideshow ? 'توقف اسلایدشو (Space)' : 'پخش اسلایدشو (Space)'}
                        ariaPressed={slideshow}
                      >
                        {slideshow ? (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <rect x="6" y="5" width="4" height="14" rx="1" />
                            <rect x="14" y="5" width="4" height="14" rx="1" />
                          </svg>
                        ) : (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <polygon points="6,4 20,12 6,20" />
                          </svg>
                        )}
                      </HudButton>
                    )}
                    <HudButton
                      onClick={toggleFs}
                      ariaLabel={isFs ? 'خروج از تمام‌صفحه (F)' : 'تمام‌صفحه (F)'}
                      ariaPressed={isFs}
                    >
                      {isFs ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="4 14 10 14 10 20" />
                          <polyline points="20 10 14 10 14 4" />
                          <line x1="14" y1="10" x2="21" y2="3" />
                          <line x1="3"  y1="21" x2="10" y2="14" />
                        </svg>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="15 3 21 3 21 9" />
                          <polyline points="9 21 3 21 3 15" />
                          <line x1="21" y1="3"  x2="14" y2="10" />
                          <line x1="3"  y1="21" x2="10" y2="14" />
                        </svg>
                      )}
                    </HudButton>
                    <HudButton onClick={onCopyUrl} ariaLabel="کپی نشانی تصویر">
                      {copied ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <rect x="9" y="9" width="13" height="13" rx="2" />
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                        </svg>
                      )}
                    </HudButton>
                    <HudButton onClick={onDownload} ariaLabel="دانلود تصویر">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                           stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                           strokeLinejoin="round" aria-hidden="true">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                    </HudButton>
                    {current?.url && (
                      <a
                        href={current.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label="باز کردن در زبانهٔ جدید"
                        className="inline-flex items-center justify-center w-8 h-8 rounded-full text-white
                                   hover:bg-white/15 transition-colors"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </a>
                    )}
                    <HudButton onClick={() => setHelpOpen((h) => !h)} ariaLabel="میان‌برهای صفحه‌کلید (?)" ariaPressed={helpOpen}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                           stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                           strokeLinejoin="round" aria-hidden="true">
                        <circle cx="12" cy="12" r="10" />
                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                    </HudButton>
                  </div>

                  {/* Dot indicator (small galleries only) */}
                  {total > 1 && total <= 8 && (
                    <div className="absolute top-3 right-1/2 translate-x-1/2 z-[5]
                                    sm:top-auto sm:bottom-[88px] sm:right-1/2
                                    hidden sm:flex items-center gap-1.5">
                      {images.map((_, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => goTo(i)}
                          aria-label={`نمایش تصویر ${formatPersianNumber(i + 1)}`}
                          aria-current={i === index}
                          className={`h-1.5 rounded-full transition-all duration-200
                                      ${i === index
                                        ? 'w-6 bg-white'
                                        : 'w-1.5 bg-white/40 hover:bg-white/70'}`}
                        />
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* ─── Filmstrip ─────────────────────────────────────────── */}
            {total > 1 && !loading && (
              <div className="relative z-[5] bg-ink-900/95 backdrop-blur
                              border-t border-white/10 px-3 md:px-4 py-3">
                <div
                  ref={stripRef}
                  className="flex gap-2 overflow-x-auto pb-1"
                  style={{ scrollbarWidth: 'none' }}
                  dir="rtl"
                >
                  {images.map((img, i) => {
                    const active = i === index;
                    return (
                      <button
                        type="button"
                        key={`${img.url}-${i}`}
                        data-thumb={i}
                        onClick={() => setIndex(i)}
                        aria-label={`نمایش تصویر ${formatPersianNumber(i + 1)}`}
                        aria-current={active}
                        className={`relative shrink-0 rounded-[14px] overflow-hidden
                                    transition-all duration-200
                                    ${active
                                      ? 'ring-2 ring-mint-500 scale-[1.05] shadow-[0_12px_28px_-8px_rgba(37,197,186,.55)]'
                                      : 'ring-1 ring-white/15 hover:ring-mint-300 hover:scale-[1.03] opacity-70 hover:opacity-100'}`}
                        style={{ width: 80, height: 60 }}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={img.url}
                          alt=""
                          loading="lazy"
                          className="w-full h-full object-cover"
                        />
                        {active && (
                          <span
                            aria-hidden="true"
                            className="absolute inset-x-0 bottom-0 h-1
                                       bg-gradient-to-l from-mint-500 to-brand-500"
                          />
                        )}
                        <span
                          aria-hidden="true"
                          className={`absolute top-1 right-1 px-1 h-4 rounded text-[9px]
                                      font-extrabold tabular-nums ring-1 ring-white/15
                                      ${active
                                        ? 'bg-mint-500 text-ink-900'
                                        : 'bg-black/55 text-white backdrop-blur-sm'}`}
                        >
                          {formatPersianNumber(i + 1)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ─── Help overlay ─────────────────────────────────────── */}
            <AnimatePresence>
              {helpOpen && (
                <motion.div
                  key="help"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 z-[20] bg-black/70 backdrop-blur-md
                             flex items-center justify-center p-6"
                  onClick={() => setHelpOpen(false)}
                >
                  <motion.div
                    initial={{ y: 16, opacity: 0, scale: 0.96 }}
                    animate={{ y: 0,  opacity: 1, scale: 1 }}
                    exit={{ y: 8,  opacity: 0, scale: 0.98 }}
                    transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                    onClick={(e) => e.stopPropagation()}
                    className="max-w-[440px] w-full bg-white rounded-[20px] p-5 md:p-6
                               text-ink-900 shadow-[0_30px_60px_-12px_rgba(0,0,0,.6)]"
                  >
                    <div className="flex items-center gap-3 mb-4">
                      <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700
                                       text-white flex items-center justify-center">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <circle cx="12" cy="12" r="10" />
                          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                          <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                      </span>
                      <div>
                        <h4 className="text-[15px] font-extrabold">میان‌برهای صفحه‌کلید</h4>
                        <p className="text-[12px] text-ink-500 font-medium">برای کاوش سریع‌تر گالری</p>
                      </div>
                    </div>
                    <ul className="grid grid-cols-1 gap-2 text-[13px]">
                      <Kbd k="→" l="تصویر قبلی" />
                      <Kbd k="←" l="تصویر بعدی" />
                      <Kbd k="Space" l="پخش / توقف اسلایدشو" />
                      <Kbd k="F" l="ورود/خروج تمام‌صفحه" />
                      <Kbd k="+ / − / 0" l="بزرگ‌نمایی / کوچک‌نمایی / بازنشانی" />
                      <Kbd k="دابل‌کلیک" l="تغییر سریع بزرگ‌نمایی" />
                      <Kbd k="Ctrl + چرخش ماوس" l="بزرگ‌نمایی پیوسته" />
                      <Kbd k="کشیدن انگشت" l="جابه‌جایی بین تصاویر" />
                      <Kbd k="Esc" l="بستن یا بازنشانی" />
                    </ul>
                    <button
                      type="button"
                      onClick={() => setHelpOpen(false)}
                      className="mt-5 w-full h-11 rounded-xl bg-brand-500 hover:bg-brand-600 active:bg-brand-700
                                 text-white font-extrabold text-[13px] transition-colors"
                    >
                      فهمیدم
                    </button>
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Internal atoms                                                           */
/* ───────────────────────────────────────────────────────────────────────── */

function HudButton({
  children, onClick, ariaLabel, disabled, ariaPressed,
}: {
  children: React.ReactNode;
  onClick: () => void;
  ariaLabel: string;
  disabled?: boolean;
  ariaPressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      aria-pressed={ariaPressed}
      className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-white
                 hover:bg-white/15 active:scale-95 transition-all duration-150
                 disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed
                 ${ariaPressed ? 'bg-white/20' : ''}`}
    >
      {children}
    </button>
  );
}

function Kbd({ k, l }: { k: string; l: string }) {
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-ink-50">
      <span className="text-ink-700 font-medium">{l}</span>
      <kbd className="font-mono text-[11.5px] font-extrabold text-ink-900
                      bg-white px-2 py-0.5 rounded-md ring-1 ring-ink-200
                      shadow-[0_1px_0_rgba(0,0,0,.06)]">
        {k}
      </kbd>
    </li>
  );
}

function Spinner() {
  return (
    <svg className="w-8 h-8 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
