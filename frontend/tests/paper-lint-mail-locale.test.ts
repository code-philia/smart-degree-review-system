import { File } from 'node:buffer';
import { afterEach, expect, it } from 'vitest';
import apiClient from '../src/api';
import { runReviewPilotPaperLint, rerunPaperLintReport } from '../src/api/paperLint';
import { getLocale, setLocale } from '../src/i18n/locale';
const adapter = apiClient.defaults.adapter;
afterEach(() => { apiClient.defaults.adapter = adapter; setLocale('zh'); });
it.each(['zh', 'en'] as const)('submits %s for both new detection and incremental rerun', async locale => {
  setLocale(locale);
  const requests: string[] = [];
  apiClient.defaults.adapter = async config => {
    requests.push(config.headers.get('X-Paper-Lint-Notification-Locale') as string);
    return { data: { job_id: 'job', status: 'pending' }, status: 202, statusText: 'Accepted', headers: {}, config };
  };
  await runReviewPilotPaperLint(new File(['%PDF-1.7\nfixture'], 'paper.pdf'), ['sjtu_rule_18']);
  await rerunPaperLintReport('report', ['sjtu_rule_22'], 'rerun');
  expect(requests).toEqual([locale, locale]);
});
it('freezes locale before asynchronous compression even when the interface language changes during upload preparation', async () => {
  setLocale('en');
  const file = new File(['%PDF-1.7\n' + 'fixture'.repeat(200000)], 'paper.pdf');
  let submitted: unknown;
  apiClient.defaults.adapter = async config => {
    submitted = config.headers.get('X-Paper-Lint-Notification-Locale');
    return { data: { job_id: 'job', status: 'pending' }, status: 202, statusText: 'Accepted', headers: {}, config };
  };
  const pending = runReviewPilotPaperLint(file, ['sjtu_rule_18']);
  setLocale('zh');
  await pending;
  expect(getLocale()).toBe('zh');
  expect(submitted).toBe('en');
});
