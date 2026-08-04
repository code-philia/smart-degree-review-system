import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

const REQ_ID = 'FEAT-NORMATIVE-REPORT';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
const scenarioText = ['摘要', '关键词：规范检测；报告导出', '引言', '这一行包含未配对（括号。。并用于报告定位。', '结论', '参考文献', '[1] 示例文献'].join('\n');

async function loginAsStudent(page) {
  await page.goto('/auth');
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(/已登录：student01/)).toBeVisible();
}

async function createCompletedReport(page) {
  const response = await page.request.post('/api/normative/detection-tasks', {
    data: {
      text: scenarioText,
      source_type: 'file',
      source_filename: 'student01-规范报告.txt',
    },
  });
  expect(response.status()).toBe(201);
  const report = await response.json();
  expect(report.status).toBe('completed');
  expect(report.rule_snapshot.length).toBeGreaterThan(0);
  expect(report.issues.length).toBeGreaterThan(0);
  expect(report.issues.some((issue) => issue.line === 4 && issue.column >= 1)).toBe(true);
  return report;
}

test.describe('FEAT-NORMATIVE-REPORT student report scenario', () => {
  test('FEAT-NORMATIVE-REPORT:SCENARIO:001 opens a completed report, locates an issue, and downloads complete UTF-8 JSON', async ({ page }) => {
    await loginAsStudent(page);
    const report = await createCompletedReport(page);

    await page.goto('/normative-reports');
    await expect(page.getByRole('heading', { name: '历史检测记录' })).toBeVisible();
    const reportRow = page.getByRole('row').filter({ hasText: 'student01-规范报告.txt' });
    await expect(reportRow).toContainText(String(report.issues.length));
    await expect(reportRow).toContainText(`${report.severity_counts.high || 0} / ${report.severity_counts.medium || 0} / ${report.severity_counts.low || 0}`);
    await reportRow.getByRole('link', { name: '报告预览' }).click();

    await expect(page).toHaveURL(new RegExp(`/normative-reports/${report.id}$`));
    await expect(page.getByRole('heading', { name: '检测报告' })).toBeVisible();
    await expect(page.getByText('问题列表')).toBeVisible();
    await expect(page.getByText('这一行包含未配对（括号。。并用于报告定位。')).toBeVisible();

    const targetIssue = report.issues.find((issue) => issue.line === 4) || report.issues[0];
    await page.getByRole('button', { name: new RegExp(`第 ${targetIssue.line} 行，第 ${targetIssue.column} 列`) }).click();
    const highlightedLine = page.getByText('这一行包含未配对（括号。。并用于报告定位。').locator('xpath=..');
    await expect(highlightedLine).toHaveClass(/bg-yellow-100/);

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载 UTF-8 JSON' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`normative-report-${report.id}.json`);
    const downloadPath = await download.path();
    if (!downloadPath) {
      throw new Error('Downloaded JSON report file path was not available');
    }
    const payload = JSON.parse(await readFile(downloadPath, 'utf8'));
    expect(payload.id).toBe(report.id);
    expect(payload.rule_snapshot).toEqual(report.rule_snapshot);
    expect(payload.issues).toEqual(report.issues);
    expect(payload.original_text).toBe(scenarioText);
  });
});
