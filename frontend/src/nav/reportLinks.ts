import { canonicalReviewUrl } from './reviewRoutes';

/** Email destinations accept one exact language parameter and no other suffix. */
export function reportReturnPath(value: unknown): string | null {
  return typeof value === 'string' && /^\/reports\/pdf\/[A-Za-z0-9-]{1,128}(?:\?lang=(?:zh|en))?$/.test(value) ? value : null;
}

export function readLinkLocale(search = ''): 'zh' | 'en' | null {
  const values = new URLSearchParams(search).getAll('lang');
  return values.length === 1 && (values[0] === 'zh' || values[0] === 'en') ? values[0] : null;
}

/** Existing route state still supports known application paths; refresh URLs only carry reports. */
export function requestedReturnTo(state: unknown, search = ''): string | null {
  const from = state && typeof state === 'object' && 'from' in state ? state.from : null;
  const saved = canonicalReviewUrl(from);
  if (saved) return saved;
  const values = new URLSearchParams(search).getAll('return_to');
  return values.length === 1 ? reportReturnPath(values[0]) : null;
}

export function signInDestination(returnTo: string, locale: string): string {
  const report = reportReturnPath(returnTo);
  return report ? '/auth?' + new URLSearchParams({ lang: readLinkLocale(report.split('?')[1]) || (locale === 'en' ? 'en' : 'zh'), return_to: report }) : '/auth';
}
