const { readFile } = require('node:fs/promises');
const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-DUPLICATION-HISTORY';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

async function createCorpusSampleForScenario(page) {
  const response = await page.request.post('/api/normative/duplication-corpus', {
    data: {
      title: `E2E 查重历史样本 ${Date.now()}`,
      subject: '管理学',
      year: 2024,
      content: [
        '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
        '平台建设需要兼顾数据共享、流程再造和持续评估。',
      ].join('\n'),
      source_type: 'paste',
      source_filename: null,
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function clearCorpus(page) {
  const listResponse = await page.request.get('/api/normative/duplication-corpus');
  expect(listResponse.status()).toBe(200);
  const body = await listResponse.json();
  for (const sample of body.samples) {
    const deleteResponse = await page.request.delete(`/api/normative/duplication-corpus/${sample.id}`);
    expect(deleteResponse.status()).toBe(204);
  }
}

async function createDuplicationDetection(page, sourceFilename, suffix) {
  const response = await page.request.post('/api/normative/duplication-detections', {
    data: {
      text: [
        '本文首先分析高校数字治理平台的建设背景。',
        '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
        `因此，本文认为相关单位应当进一步完善制度设计，提升协同治理能力。${suffix}`,
      ].join('\n'),
      source_type: 'file',
      source_filename: sourceFilename,
    },
  });
  expect(response.status()).toBe(201);
  const report = await response.json();
  expect(report.status).toBe('completed');
  expect(report.sample_count).toBeGreaterThan(0);
  expect(report.total_similarity_rate).toBeGreaterThan(0);
  return report;
}

test.describe('FEAT-DUPLICATION-HISTORY student history scenario', () => {
  test('FEAT-DUPLICATION-HISTORY:SCENARIO:001 student sees only own two records in reverse time order and opens the full report', async ({ page }) => {
    await loginAs(page, 'school_admin01');
    await clearCorpus(page);
    await createCorpusSampleForScenario(page);

    await loginAs(page, 'supervisor01');
    await createDuplicationDetection(page, `supervisor-hidden-${Date.now()}.txt`, '导师记录不可见');

    await loginAs(page, 'student01');
    const olderReport = await createDuplicationDetection(page, `student01-history-old-${Date.now()}.txt`, '第一次检测');
    const newerReport = await createDuplicationDetection(page, `student01-history-new-${Date.now()}.txt`, '第二次检测');

    await page.goto('/duplication-history');
    await expect(page.getByRole('heading', { name: '历史检测记录' })).toBeVisible();
    const rows = page.getByRole('row');
    const newerRow = rows.filter({ hasText: newerReport.source_filename });
    const olderRow = rows.filter({ hasText: olderReport.source_filename });
    await expect(newerRow).toBeVisible();
    await expect(olderRow).toBeVisible();
    await expect(page.getByText(/supervisor-hidden-/)).toHaveCount(0);
    await expect(newerRow).toContainText('总相似率');
    await expect(newerRow).toContainText('写作风险分');
    await expect(newerRow).toContainText(`样本库数量：${newerReport.sample_count}`);
    await expect(newerRow).toContainText(String(newerReport.risk.score));
    await expect(newerRow).toContainText(String(Math.round(newerReport.total_similarity_rate * 100)));

    const newerBox = await newerRow.boundingBox();
    const olderBox = await olderRow.boundingBox();
    expect(newerBox).not.toBeNull();
    expect(olderBox).not.toBeNull();
    expect(newerBox.y).toBeLessThan(olderBox.y);

    await newerRow.getByRole('link', { name: '报告预览' }).click();
    await expect(page).toHaveURL(new RegExp(`/duplication-history/${newerReport.id}$`));
    await expect(page.getByRole('heading', { name: '查重检测报告' })).toBeVisible();
    await expect(page.getByText(newerReport.source_filename)).toBeVisible();
    await expect(page.getByText(/总相似率/)).toBeVisible();
    await expect(page.getByText(/写作风险分/)).toBeVisible();
    await expect(page.getByText(/样本库数量/)).toBeVisible();
    await expect(page.getByText(/高校数字治理平台的建设效果/)).toBeVisible();
    await expect(page.getByRole('button', { name: '浏览器打印' })).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载 UTF-8 JSON' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`duplication-report-${newerReport.id}.json`);
    const downloadPath = await download.path();
    if (!downloadPath) {
      throw new Error('Downloaded duplication JSON report file path was not available');
    }
    const payload = JSON.parse(await readFile(downloadPath, 'utf8'));
    expect(payload.id).toBe(newerReport.id);
    expect(payload.source_filename).toBe(newerReport.source_filename);
    expect(payload.total_similarity_rate).toBe(newerReport.total_similarity_rate);
    expect(payload.writing_risk_score).toBe(newerReport.risk.score);
    expect(payload.sample_count).toBe(newerReport.sample_count);
    expect(payload.report_json.top_matches).toEqual(newerReport.top_matches);
  });
});
