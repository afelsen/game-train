import type { RuntimeRequest } from './contracts';
import { BrowserPlayRuntime } from './browser-runtime';

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NODE_ENV === 'development' ? 'http://localhost:8000' : '')
).replace(/\/$/, '');

export const DEFAULT_PROVIDER_ID = API_URL
  ? 'fullhouse-deep-cfr-experimental-hu'
  : 'check-call-hu';
export const REMOTE_ANALYSIS_AVAILABLE = Boolean(API_URL);

export const remoteRequest: RuntimeRequest = async <T>(path: string, options?: RequestInit) => {
  if (!API_URL) throw new Error('This model requires the optional Game Train API');
  const headers = new Headers(options?.headers);
  headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const data: unknown = await response.json();
  if (!response.ok) {
    const message = typeof data === 'object' && data !== null && 'error' in data
      ? String(data.error)
      : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data as T;
};

const browserRuntime = new BrowserPlayRuntime(remoteRequest);

/**
 * One transport-neutral request function for the UI.
 *
 * `browser` (default): Play state/rules/history live in the browser; model and
 * analysis routes use the optional API. `server`: preserves the legacy fully
 * server-authoritative runtime for debugging and parity checks.
 */
export const runtimeRequest: RuntimeRequest =
  process.env.NEXT_PUBLIC_PLAY_RUNTIME === 'server'
    ? remoteRequest
    : browserRuntime.request.bind(browserRuntime);
