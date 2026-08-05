const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-REPORT-STUDENT-SUBMIT';
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

async function createCompletedNormativeReport(page, sourceFilename) {
  const response = await page.request.post('/api/normative/detection-tasks', {
    data: {
      text: ['摘要', '关键词：学生报告提交', '引言', '研究方法', '结论', '参考文献', '[1] 示例文献'].join('\n'),
      source_type: 'file',
      source_filename: sourceFilename,
    },
  });
  expect(response.status()).toBe(201);
  const report = await response.json();
  expect(report.status).toBe('completed');
  return report;
}

test.describe('FEAT-REPORT-STUDENT-SUBMIT student submission scenarios', () => {
  test('FEAT-REPORT-STUDENT-SUBMIT:E2E:SCENARIO:001 student01 submits an owned completed report and supervisor01 receives a todo', async ({ page }) => {
    await loginAs(page, 'student01');
    const report = await createCompletedNormativeReport(page, `student01-submit-${Date.now()}.txt`);

    await page.goto('/student-report-submissions');
    await expect(page.getByRole('heading', { name: '学生报告提交与批阅结果台账' })).toBeVisible();
    const reportRow = page.getByRole('row').filter({ hasText: report.source_filename });
    await expect(reportRow).toBeVisible();
    await reportRow.getByRole('checkbox', { name: new RegExp(report.id) }).check();
    const submissionResponsePromise = page.waitForResponse((response) => (
      response.url().endsWith('/api/normative/report-submissions') && response.request().method() === 'POST'
    ));
    await page.getByRole('button', { name: '推送报告' }).click();
    const submissionResponse = await submissionResponsePromise;

    await expect(page.getByText(/已创建批次/)).toBeVisible();
    await expect(page.getByText(/待批阅记录 1 条/)).toBeVisible();

    expect(submissionResponse.status()).toBe(201);
    const body = await submissionResponse.json();
    expect(body.submissions[0]).toMatchObject({
      student_id: 'student01',
      supervisor_id: 'supervisor01',
      source_type: 'normative',
      report_id: report.id,
      status: 'submitted_pending_review',
    });
    expect(body.todos[0]).toMatchObject({
      submission_id: body.submissions[0].id,
      assignee_id: 'supervisor01',
      actor_id: 'student01',
      status: 'pending',
    });
  });

  test('FEAT-REPORT-STUDENT-SUBMIT:E2E:SCENARIO:002 backend rejects another user report id with 403 and no created records', async ({ page }) => {
    await loginAs(page, 'supervisor01');
    const foreignReport = await createCompletedNormativeReport(page, `supervisor-submit-denied-${Date.now()}.txt`);

    await loginAs(page, 'student01');
    const response = await page.request.post('/api/normative/report-submissions', {
      data: { reports: [{ source_type: 'normative', report_id: foreignReport.id }] },
    });

    expect(response.status()).toBe(403);
    const body = await response.json();
    expect(body).toMatchObject({ code: 403 });
    expect(body.submissions).toBeUndefined();
    expect(body.todos).toBeUndefined();
  });
});
