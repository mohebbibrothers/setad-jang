import { cn } from '@/lib/utils';

/**
 * Single source of truth for all line icons used across the site.
 * Each icon ships with a proper viewBox + stroke setup so it scales
 * cleanly at any size without clipping (the previous bug).
 *
 * Use as: <Icon name="search" className="w-5 h-5" />
 */

export type IconName =
  | 'search' | 'menu' | 'close' | 'chevron-down' | 'chevron-left' | 'chevron-right'
  | 'login' | 'plus' | 'send' | 'paperclip' | 'attach' | 'check' | 'eye' | 'heart' | 'link'
  | 'instagram' | 'twitter' | 'linkedin' | 'telegram' | 'aparat'
  | 'user' | 'users' | 'phone' | 'id-card' | 'category-pick' | 'message-square'
  | 'map-pin' | 'clock' | 'tag' | 'shield' | 'handshake' | 'megaphone'
  | 'helping-hand' | 'graduation' | 'scale' | 'flag' | 'hand-heart'
  | 'sparkles' | 'play' | 'arrow-left' | 'filter' | 'grid' | 'list'
  | 'heart-handshake' | 'gavel' | 'gift';

type Props = {
  name: IconName;
  className?: string;
  /** Visually-hidden label for screen readers. If omitted, icon is decorative. */
  label?: string;
  strokeWidth?: number;
};

export function Icon({ name, className, label, strokeWidth = 2 }: Props) {
  const aria = label
    ? { role: 'img' as const, 'aria-label': label }
    : { 'aria-hidden': true };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn('inline-block flex-shrink-0', className)}
      {...aria}
    >
      {PATHS[name]}
    </svg>
  );
}

const PATHS: Record<IconName, JSX.Element> = {
  'search': (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ),
  'menu': (
    <>
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </>
  ),
  'close': (
    <>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </>
  ),
  'chevron-down': <polyline points="6 9 12 15 18 9" />,
  'chevron-left': <polyline points="15 6 9 12 15 18" />,
  'chevron-right': <polyline points="9 6 15 12 9 18" />,
  'arrow-left': (
    <>
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </>
  ),
  'login': (
    <>
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </>
  ),
  'plus': (
    <>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </>
  ),
  'send': (
    <g transform="rotate(-45 12 12)">
      <path d="M22 2 11 13" />
      <path d="M22 2 15 22 11 13 2 9z" />
    </g>
  ),
  'paperclip': <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />,
  'attach':    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />,
  'check': <polyline points="20 6 9 17 4 12" />,
  'eye': (
    <>
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  'heart': <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 1 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />,
  'link': (
    <>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </>
  ),
  'instagram': (
    <>
      <rect x="3" y="3" width="18" height="18" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="0.5" fill="currentColor" stroke="none" />
    </>
  ),
  'twitter': <path d="M22 4.01c-1 .49-1.98.689-3 .99-1.121-1.265-2.783-1.335-4.38-.737S11.977 6.323 12 8v1c-3.245.083-6.135-1.395-8-4 0 0-4.182 7.433 4 11-1.872 1.247-3.739 2.088-6 2 3.308 1.803 6.913 2.423 10.034 1.517 3.58-1.04 6.522-3.723 7.651-7.742a13.84 13.84 0 0 0 .497-3.753C21.998 7.773 23.5 5.755 22 4.01z" />,
  'linkedin': (
    <>
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect x="2" y="9" width="4" height="12" />
      <circle cx="4" cy="4" r="2" />
    </>
  ),
  'telegram': <path d="M21.5 4.5 2.5 11.5l5 2 2 6 3-4 5 4 4-15z" />,
  'aparat': (
    <>
      <circle cx="12" cy="12" r="9" />
      <polygon points="10 8 16 12 10 16" fill="currentColor" stroke="none" />
    </>
  ),
  'user': (
    <>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </>
  ),
  'users': (
    <>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  'phone': <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />,
  'id-card': (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="11" r="2" />
      <path d="M5 18c1-2 3-3 4-3s3 1 4 3" />
      <line x1="14" y1="9" x2="19" y2="9" />
      <line x1="14" y1="13" x2="19" y2="13" />
    </>
  ),
  'category-pick': (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  'message-square': <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />,
  'map-pin': (
    <>
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </>
  ),
  'clock': (
    <>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 16 14" />
    </>
  ),
  'tag': (
    <>
      <path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </>
  ),
  'shield': <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  'handshake': <path d="M8.5 14.5 4 19a2.121 2.121 0 0 0 0 3 2.121 2.121 0 0 0 3 0l4-4M14 7l3-3 4 4-3 3M9 11l5-5 4 4-5 5z" />,
  'megaphone': (
    <>
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
    </>
  ),
  'helping-hand': (
    <>
      <path d="M11 13a2 2 0 1 0 4 0v-3l5 2v6a4 4 0 0 1-4 4H8l-5-5 3-3h2" />
      <path d="M11 13V5a2 2 0 1 1 4 0v5" />
    </>
  ),
  'graduation': (
    <>
      <path d="M22 10v6" />
      <path d="M2 10l10-5 10 5-10 5z" />
      <path d="M6 12v5c3 3 9 3 12 0v-5" />
    </>
  ),
  'scale': (
    <>
      <path d="M12 3v18" />
      <path d="M3 8h18" />
      <path d="M7 8l-3 7a4 4 0 0 0 6 0z" />
      <path d="M17 8l3 7a4 4 0 0 1-6 0z" />
      <path d="M8 21h8" />
    </>
  ),
  'flag': (
    <>
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
      <line x1="4" y1="22" x2="4" y2="15" />
    </>
  ),
  'hand-heart': (
    <>
      <path d="M11 14h2l3-3 4 4-7 7-7-7 1-1" />
      <path d="M5 12l-3-3 4-4 3 3" />
    </>
  ),
  'sparkles': <path d="M12 3l1.9 5.8H20l-4.9 3.6 1.9 5.8L12 14.6 7 18.2l1.9-5.8L4 8.8h6.1z" />,
  'play': <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none" />,
  'filter': <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />,
  'grid': (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  'list': (
    <>
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <circle cx="4" cy="6" r="1" />
      <circle cx="4" cy="12" r="1" />
      <circle cx="4" cy="18" r="1" />
    </>
  ),
  /* Campaign-style "heart on a handshake" — pillar icon for مددکاری */
  'heart-handshake': (
    <>
      <path d="M11 17 9 19l-1.5 1.5a1.121 1.121 0 1 1-1.6-1.6L7 18" />
      <path d="m21 3 1 7-7 1 1-5-9 9-5-5 9-9 5 1z" />
      <path d="M3 11v5a2 2 0 0 0 2 2h3" />
      <path d="M9 18a4 4 0 0 1 4-4h2a4 4 0 0 1 4 4v3" />
    </>
  ),
  /* Gavel — pillar icon for R4J / justice */
  'gavel': (
    <>
      <path d="m14.5 12.5-8 8a2.121 2.121 0 1 1-3-3l8-8" />
      <path d="m16 16 6-6" />
      <path d="m8 8 6-6" />
      <path d="m9 7 8 8" />
      <path d="m21 11-8-8" />
    </>
  ),
  /* Gift — pillar icon for دیوار مهربانی */
  'gift': (
    <>
      <rect x="3" y="8" width="18" height="4" rx="1" />
      <path d="M12 8v13" />
      <path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7" />
      <path d="M7.5 8a2.5 2.5 0 0 1 0-5C9 3 12 5 12 8c0-3 3-5 4.5-5a2.5 2.5 0 0 1 0 5" />
    </>
  ),
};
