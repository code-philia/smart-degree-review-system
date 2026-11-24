const fs = require('node:fs');
const { test, expect, open, PDF_FIXTURE } = require('../support.cjs');
test.use({ role: 'student' });
const asJson = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
async function readyUpload(page, { file = true } = {}) {
  await open(page, '/paper-upload');
  await expect(page.getByRole('button', { name: '展开选择', exact: true })).toBeEnabled();
  if (file) await page.getByLabel('上传待审查 PDF').setInputFiles(PDF_FIXTURE);
  await page.getByRole('button', { name: '展开选择', exact: true }).click();
}
const start = page => page.getByRole('button', { name: '开始检测', exact: true });
async function onlyFree(page) {
  await page.getByRole('button', { name: '清空全部检测规则', exact: true }).click();
  await page.getByRole('checkbox', { name: /^关键词数量/ }).check();
}
test('[injected] catalog server error is recoverable through its retry control', async ({ page, facts }) => {
  let fail = true;
  await page.route('**/api/normative/paper-lint/rules*', r => fail ? asJson(r, { message: '测试规则目录加载失败' }, 503) : asJson(r, facts.catalog));
  await open(page, '/paper-upload');
  await expect(page.getByRole('alert')).toContainText('测试规则目录加载失败');
  fail = false; await page.getByRole('button', { name: '重新加载', exact: true }).click();
  await expect(page.getByRole('button', { name: '展开选择', exact: true })).toBeEnabled();
});
for (const language of ['zh', 'en']) test(`[injected] zero credit in ${language} explains that free rules remain usable`, async ({ page, facts }) => {
  const zero = { ...facts.credit, available_cny: '0.000000000', spent_cny: '100.000000000', reserved_cny: '0.000000000', remaining_percent: 0 };
  await page.route('**/api/normative/paper-lint/credit', r => asJson(r, zero));
  await open(page, '/paper-upload?lang=' + language);
  const expand = page.getByRole('button', { name: language === 'zh' ? '展开选择' : 'Choose checks', exact: true });
  await expect(expand).toBeEnabled(); await expand.click();
  await page.getByLabel(language === 'zh' ? '上传待审查 PDF' : 'Choose a thesis PDF').setInputFiles(PDF_FIXTURE);
  await expect(page.getByText(language === 'zh' ? '额度不足' : 'Insufficient credit', { exact: true })).toBeVisible();
  await expect(page.getByText(language === 'zh' ? '取消需要额度的规则后，仍可使用免费规则进行检测。' : 'Deselect checks that use credit to continue with free checks.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: language === 'zh' ? '开始检测' : 'Start review', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: language === 'zh' ? '清空全部检测规则' : 'Clear all checks', exact: true }).click();
  await page.getByRole('checkbox', { name: language === 'zh' ? /^关键词数量/ : /^Keyword count/ }).check();
  await expect(page.getByRole('button', { name: language === 'zh' ? '开始检测' : 'Start review', exact: true })).toBeEnabled();
});
test('[injected] credit service outage blocks paid checks but permits free-only checks', async ({ page }) => {
  await page.route('**/api/normative/paper-lint/credit', r => asJson(r, { message: '测试额度服务不可用' }, 503));
  await readyUpload(page); await expect(start(page)).toBeDisabled();
  await onlyFree(page); await expect(start(page)).toBeEnabled();
});
for (const status of [403, 500]) test(`[injected] history ${status} is distinguishable from a valid empty history`, async ({ page }) => {
  await page.route('**/api/normative/paper-lint/reports', r => asJson(r, { message: '测试历史记录读取失败' }, status));
  await open(page, '/reports');
  // An unavailable/forbidden data source must not be presented as a successful empty account.
  await expect(page.getByText('暂无检测记录', { exact: true })).not.toBeVisible();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('测试历史记录读取失败');
});
test('[injected] legitimate empty history has a clear upload action', async ({ page }) => {
  await page.route('**/api/normative/paper-lint/reports', r => asJson(r, { records: [] }));
  await open(page, '/reports');
  await expect(page.getByText('暂无检测记录', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /开始|上传|检测/ }).last()).toBeVisible();
});
for (const failure of ['invalid-pdf', 'server-error']) test(`[injected] ${failure} submission shows a meaningful error and preserves the selected PDF`, async ({ page }) => {
  await page.route('**/api/normative/paper-lint/run?*', r => asJson(r, { message: failure === 'invalid-pdf' ? '上传文件不是可读取的 PDF' : '检测服务暂不可用，请稍后重试' }, failure === 'invalid-pdf' ? 400 : 503));
  await readyUpload(page); await onlyFree(page); await start(page).click();
  await expect(page.getByText(failure === 'invalid-pdf' ? '上传文件不是可读取的 PDF' : '检测服务暂不可用，请稍后重试', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '移除文件', exact: true })).toBeVisible();
});
function job(facts, status = 'pending', extra = {}) {
  return { job_id: 'gui-injected-job', user_id: facts.studentUser.id, source_filename: 'local-four-rule-sample.pdf', selected_rule_ids: ['keyword_count_check'], status,
    report_id: null, error_message: null, queue_position: 101, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), ...extra };
}
test('[injected] queued request stays visible, prevents duplicate submission, and can be stopped', async ({ page, facts }) => {
  let stopped = false, posts = 0;
  await page.route('**/api/normative/paper-lint/run?*', r => { posts++; return asJson(r, job(facts)); });
  await page.route('**/api/normative/paper-lint/jobs/gui-injected-job', r => asJson(r, job(facts, stopped ? 'cancelled' : 'pending')));
  await page.route('**/api/normative/paper-lint/jobs/gui-injected-job/cancel', r => { stopped = true; return asJson(r, job(facts, 'cancelled')); });
  await readyUpload(page); await onlyFree(page); await start(page).click();
  await expect(page.getByRole('button', { name: '停止检测', exact: true })).toBeEnabled();
  await expect(page.getByText(/前方还有 100 个任务/)).toBeVisible();
  await expect(page.getByRole('button', { name: '检测进行中', exact: true })).toBeDisabled();
  expect(posts).toBe(1);
  await page.getByRole('button', { name: '停止检测', exact: true }).click();
  await expect(page.getByText('已停止检测，可以重新开始。', { exact: true })).toBeVisible();
});
test('[injected] a completed job without a report is not treated as successful review', async ({ page, facts }) => {
  await page.route('**/api/normative/paper-lint/run?*', r => asJson(r, job(facts)));
  await page.route('**/api/normative/paper-lint/jobs/gui-injected-job', r => asJson(r, job(facts, 'completed')));
  await readyUpload(page); await onlyFree(page); await start(page).click();
  await expect(page.getByText('检测完成，但报告未保存，请重试', { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page).toHaveURL(/\/paper-upload/);
});
test('[injected] feedback service failure preserves draft and retry request identity', async ({ page }) => {
  const inputs = [];
  await page.route('**/api/normative/feedback/system-feedback', r => { inputs.push(r.request().postDataJSON()); return asJson(r, { message: '测试反馈保存失败' }, 503); });
  await open(page, '/paper-upload');
  await page.getByRole('button', { name: '使用反馈', exact: true }).click();
  const dialog = page.getByRole('dialog');
  // The visible star decorates a clipped native radio. Select it through its native keyboard interaction.
  const rating = dialog.getByRole('radio', { name: '3 星', exact: true });
  await rating.focus(); await rating.press('Space');
  await dialog.getByLabel('补充意见（可选）').fill('GUI_TEST intercepted retry draft');
  await dialog.getByRole('button', { name: '提交反馈', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('测试反馈保存失败');
  await expect(dialog.getByLabel('补充意见（可选）')).toHaveValue('GUI_TEST intercepted retry draft');
  await dialog.getByRole('button', { name: '提交反馈', exact: true }).click();
  await expect.poll(() => inputs.length).toBe(2);
  expect(inputs[0].request_id).toBe(inputs[1].request_id);
});
