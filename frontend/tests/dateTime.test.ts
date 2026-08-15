import { describe, expect, it } from 'vitest';
import { formatChinaDateTime } from '../src/utils/dateTime';

describe('formatChinaDateTime', () => {
  it('formats ISO UTC timestamps in China Standard Time without machine formatting', () => {
    expect(formatChinaDateTime('2026-08-12T03:00:00.000Z')).toBe('2026-08-12 11:00');
  });

  it('keeps invalid values visible and handles missing values', () => {
    expect(formatChinaDateTime('not-a-date')).toBe('not-a-date');
    expect(formatChinaDateTime(null)).toBe('—');
  });
});
