import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DailyQuotaHint } from '../src/components/paperLint/DailyQuotaHint';
import { usePaperLintDailyQuota } from '../src/hooks/usePaperLintDailyQuota';
import { fetchPaperLintDailyQuota } from '../src/api/paperLint';
import { setLocale, translate } from '../src/i18n/locale';
vi.mock('../src/api/paperLint', async () => ({ ...await vi.importActual('../src/api/paperLint'), fetchPaperLintDailyQuota: vi.fn() }));
const sample = (extra = {}) => ({ limited: true, limit: 3, used: 1, reserved: 0, remaining: 2,
  day: '2026-11-12', resets_at: '2026-11-12T16:00:00.000Z', server_time: '2026-11-12T02:00:00.000Z', timezone: 'Asia/Shanghai', ...extra });
beforeEach(() => { vi.mocked(fetchPaperLintDailyQuota).mockResolvedValue(sample()); setLocale('zh'); });
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers(); setLocale('zh'); });
it('shows a compact remaining count and hides the limit for administrators', () => {
  const view = render(<DailyQuotaHint quota={sample()} />);
  expect(screen.getByText('今日剩余 2 / 3 次')).toBeVisible();
  view.rerender(<DailyQuotaHint quota={sample({limited:false, remaining:null})} />);
  expect(screen.queryByText(/今日剩余/)).not.toBeInTheDocument();
});
it('distinguishes successful usage from temporary reservations', () => {
  const view = render(<DailyQuotaHint quota={sample({used:3, remaining:0})} />);
  expect(screen.getByText('今日次数已用完')).toBeVisible();
  view.rerender(<DailyQuotaHint quota={sample({used:1, reserved:2, remaining:0})} />);
  expect(screen.getByText('可用次数已暂占')).toBeVisible();
  expect(screen.queryByText('今日次数已用完')).not.toBeInTheDocument();
});
it('uses readable English for counts and quota errors', () => {
  setLocale('en'); render(<DailyQuotaHint quota={sample()} />);
  expect(screen.getByText('2 / 3 left today')).toBeVisible();
  expect(translate('今日检测次数已用完，请于北京时间明日00:00后重试。')).toContain('00:00');
  expect(translate('当前可用检测次数已被进行中的任务占用，请在任务结束或取消后重试。')).toMatch(/ongoing reviews/);
});
it('refreshes after job transitions, focus and another tab, and restores failed/cancelled reservations', async () => {
  vi.mocked(fetchPaperLintDailyQuota).mockResolvedValueOnce(sample({reserved:1,remaining:1}));
  const view = renderHook(({key}) => usePaperLintDailyQuota('student',key), {initialProps:{key:'running'}});
  await waitFor(() => expect(view.result.current.quota?.remaining).toBe(1));
  view.rerender({key:'cancelled'});
  await waitFor(() => expect(view.result.current.quota?.remaining).toBe(2));
  fireEvent(window,new Event('focus'));
  await waitFor(() => expect(fetchPaperLintDailyQuota).toHaveBeenCalledTimes(3));
  fireEvent(window,new StorageEvent('storage',{key:'paper-lint-active-job:student'}));
  await waitFor(() => expect(fetchPaperLintDailyQuota).toHaveBeenCalledTimes(4));
});
it('refreshes at Shanghai midnight using the server clock, not the browser timezone', async () => {
  vi.useFakeTimers();
  vi.mocked(fetchPaperLintDailyQuota).mockResolvedValueOnce(sample({used:3,remaining:0,server_time:'2026-11-12T15:59:59.000Z'}))
    .mockResolvedValueOnce(sample({used:0,remaining:3,day:'2026-11-13',resets_at:'2026-11-13T16:00:00.000Z',server_time:'2026-11-12T16:00:00.100Z'}));
  const view = renderHook(() => usePaperLintDailyQuota('student'));
  await act(async()=>{});
  expect(view.result.current.quota?.remaining).toBe(0);
  await act(async()=>{ await vi.advanceTimersByTimeAsync(1200); });
  expect(view.result.current.quota?.remaining).toBe(3);
  view.unmount(); expect(vi.getTimerCount()).toBe(0);
});
it('does not invent an allowance on failure or carry another account’s allowance across login', async () => {
  const view = renderHook(({id}) => usePaperLintDailyQuota(id),{initialProps:{id:'student'}});
  await waitFor(()=>expect(view.result.current.quota?.remaining).toBe(2));
  vi.mocked(fetchPaperLintDailyQuota).mockRejectedValue(new Error('offline'));
  view.rerender({id:'other'});
  await waitFor(()=>expect(view.result.current.error).toBe(true));
  expect(view.result.current.quota).toBeNull();
});
