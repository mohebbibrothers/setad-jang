import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Tailwind-merge + clsx helper for safe className composition. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Format integer using Persian locale (٬ thousands separator and Persian digits). */
export function formatPersianNumber(value: number | string): string {
  const n = typeof value === 'string' ? Number(value) : value;
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString('fa-IR');
}

/** Format a Toman/Rial currency amount in Persian. */
export function formatToman(amount: number): string {
  return `${formatPersianNumber(amount)} تومان`;
}

/** Convert any digits in a string to Persian digits. */
export function toPersianDigits(input: string | number): string {
  const map = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  return String(input).replace(/[0-9]/g, (d) => map[Number(d)]);
}

/** Truncate a long text safely with an ellipsis. */
export function truncate(text: string, maxLen = 120): string {
  if (!text) return '';
  return text.length <= maxLen ? text : `${text.slice(0, maxLen).trim()}…`;
}
