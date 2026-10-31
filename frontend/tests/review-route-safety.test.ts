import { expect, it } from 'vitest';
import { canonicalReviewUrl, reportDetailPath } from '../src/nav/reviewRoutes';

it.each([
  ['/paper-upload', '/paper-upload'],
  ['/abstract-check?source=login#rules', '/abstract-check?source=login#rules'],
  ['/reports/', '/reports'],
  ['/reports/pdf/id%2Fone?view=pdf#page=2', '/reports/pdf/id%2Fone?view=pdf#page=2'],
  ['/thirty-rules-check/reports/pdf/id%2Fone?view=pdf#page=2', '/reports/pdf/id%2Fone?view=pdf#page=2'],
])('preserves a known local return URL %s', (input, target) => {
  expect(canonicalReviewUrl(input)).toBe(target);
});

it.each([undefined, null, {}, 'https://example.com/', '//example.com/', '/auth', '/reports-other',
  '/reports/pdf/id/other', '/reports\\@example.com', '/reports\n', ' /reports'])('rejects unknown, external or malformed destinations %s', input => {
  expect(canonicalReviewUrl(input)).toBeNull();
});

it('encodes a report ID once when building a detail link', () => {
  expect(reportDetailPath('论文 / #1')).toBe('/reports/pdf/%E8%AE%BA%E6%96%87%20%2F%20%231');
});
