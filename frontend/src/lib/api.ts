/**
 * Lightweight typed API client for the Django DRF backend.
 *
 * Backend response envelope (from apps/core/responses.py):
 *   { success: true, status_code: 200, message: string, data: T }
 *   { success: false, status_code: 4xx/5xx, message: string, errors: object }
 *
 * This client unwraps `data` on success and throws ApiError on failure.
 * In SSR it talks directly to NEXT_PUBLIC_API_URL; in the browser it
 * can use the same-origin /api/proxy path (configured in next.config.mjs).
 */

import { siteConfig } from './site';

export type ApiEnvelope<T> = {
  success: boolean;
  status_code: number;
  message: string;
  data?: T;
  errors?: Record<string, unknown>;
};

export class ApiError extends Error {
  status: number;
  errors?: Record<string, unknown>;
  constructor(message: string, status: number, errors?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errors = errors;
  }
}

export type FetchOptions = RequestInit & {
  /** Use absolute backend URL even in browser (skip same-origin proxy). */
  absolute?: boolean;
  /** Cache + revalidate hints for Next.js fetch. */
  revalidate?: number | false;
  tags?: string[];
  /** AbortSignal for in-flight cancellation (live search, etc). */
  signal?: AbortSignal;
};

function resolveBaseUrl(absolute: boolean): string {
  const isServer = typeof window === 'undefined';
  if (isServer || absolute) {
    return `${siteConfig.apiUrl.replace(/\/+$/, '')}/api/v1`;
  }
  return '/api/proxy';
}

export async function apiFetch<T = unknown>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { absolute = false, revalidate, tags, headers, ...init } = options;
  const base = resolveBaseUrl(absolute);
  const url = `${base}${path.startsWith('/') ? path : `/${path}`}`;

  const nextOptions: { revalidate?: number | false; tags?: string[] } = {};
  if (revalidate !== undefined) nextOptions.revalidate = revalidate;
  if (tags) nextOptions.tags = tags;

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        'Accept': 'application/json',
        'Accept-Language': 'fa-IR',
        ...(init.body && !(init.body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...(headers as Record<string, string> | undefined),
      },
      // Next.js-specific `next` fetch option. Newer Next types include
      // it, so we no longer need a @ts-expect-error suppression.
      next: Object.keys(nextOptions).length ? nextOptions : undefined,
    });
  } catch (err) {
    throw new ApiError(
      err instanceof Error ? err.message : 'خطای شبکه',
      0,
    );
  }

  let payload: ApiEnvelope<T> | null = null;
  try {
    payload = (await res.json()) as ApiEnvelope<T>;
  } catch {
    // non-JSON response (e.g. HTML error page)
  }

  if (!res.ok || (payload && payload.success === false)) {
    throw new ApiError(
      payload?.message || `درخواست با خطا مواجه شد (${res.status})`,
      res.status,
      payload?.errors,
    );
  }

  return (payload?.data ?? (payload as unknown)) as T;
}

/** Safe SSR fetch — returns null instead of throwing (for graceful UI fallbacks). */
export async function safeApiFetch<T = unknown>(
  path: string,
  options: FetchOptions = {},
): Promise<T | null> {
  try {
    return await apiFetch<T>(path, options);
  } catch {
    return null;
  }
}
