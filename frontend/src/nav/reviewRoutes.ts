export const REVIEW_ROUTES = {
  upload: '/paper-upload',
  semantic: '/abstract-check',
  history: '/reports',
} as const;

export function reportDetailPath(reportId: string) {
  return `${REVIEW_ROUTES.history}/pdf/${encodeURIComponent(reportId)}`;
}

/** Resolve only known, same-app destinations, including saved legacy links. */
export function canonicalReviewUrl(value: unknown): string | null {
  if (typeof value !== 'string' || /[\\\u0000-\u0020\u007f]/.test(value)) return null;
  const match = /^([^?#]*)([?#].*)?$/.exec(value);
  if (!match) return null;
  const path = match[1].replace(/\/$/, '');
  const suffix = match[2] || '';
  const aliases: Record<string, string> = {
    '/thirty-rules-check': REVIEW_ROUTES.upload,
    '/semantic-rules-check': REVIEW_ROUTES.semantic,
    '/thirty-rules-check/reports': REVIEW_ROUTES.history,
  };
  if (aliases[path]) return aliases[path] + suffix;
  if (Object.values(REVIEW_ROUTES).some((route) => route === path)) return path + suffix;
  const report = /^\/(?:thirty-rules-check\/reports|reports)\/pdf\/([^/]+)$/.exec(path);
  return report ? `${REVIEW_ROUTES.history}/pdf/${report[1]}${suffix}` : null;
}
