const { test, expect } = require('@playwright/test');
const { get, run } = require('../src/database');

const REQ_ID = 'FEAT-REPORT-STUDENT-RESULTS';
void REQ_ID;

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

async function clearStudentResultsData() {
  await run('DELETE FROM supervisor_review_feedback');
  await run('DELETE FROM in_app_todos');
  await run('DELETE FROM report_submissions');
}

async function seedReviewedSubmission(overrides = {}) {
  const submissionId = overrides.submission_id;
  await run(
    `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      submissionId,
      overrides.batch_id || `${submissionId}-batch`,
      overrides.student_id || 'student01',
      overrides.supervisor_id || 'supervisor01',
      overrides.source_type || 'normative',
      overrides.report_id || `${submissionId}-report`,
      overrides.status || 'review_completed_feedback',
      overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
  await run(
    `INSERT INTO supervisor_review_feedback (id, submission_id, supervisor_id, annotations_json, overall_evaluation, improvement_suggestions, locked_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      `${submissionId}-feedback`,
      submissionId,
      overrides.supervisor_id || 'supervisor01',
      JSON.stringify(overrides.annotations || [{ finding_id: 'finding-001', comment: '请补充该 finding 的定位依据。' }]),
      overrides.overall_evaluation || '整体评价：批阅完成，学生首次打开后应标记已查阅。',
      overrides.improvement_suggestions || '整改建议：下一轮提交前逐条回复导师批注。',
      overrides.locked_at || '2026-08-05T10:00:00.000Z',
    ],
  );
  return submissionId;
}

async function prepareScenarioData() {
  await clearStudentResultsData();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const submissionId = await seedReviewedSubmission({
    submission_id: `student-result-e2e-${suffix}`,
    batch_id: `student-result-e2e-batch-${suffix}`,
    report_id: `student-result-e2e-report-${suffix}`,
    status: 'review_completed_feedback',
    annotations: [{ finding_id: 'finding-001', comment: `请补充该 finding 的定位依据 ${suffix}` }],
    overall_evaluation: `整体评价：批阅完成 ${suffix}`,
    improvement_suggestions: `整改建议：下一轮提交前逐条回复批注 ${suffix}`,
  });
  await seedReviewedSubmission({
    submission_id: `student-result-history-${suffix}`,
    batch_id: `student-result-e2e-batch-${suffix}`,
    report_id: `student-result-e2e-report-${suffix}`,
    status: 'student_viewed_feedback',
    created_at: '2026-08-04T09:00:00.000Z',
  });
  return { suffix, submissionId };
}

async function readSubmissionStatus(submissionId) {
  const row = await get('SELECT status FROM report_submissions WHERE id = ?', [submissionId]);
  return row?.status;
}

test.describe('FEAT-REPORT-STUDENT-RESULTS scenarios', () => {
  test('FEAT-REPORT-STUDENT-RESULTS:E2E:SCENARIO:001 student01 opens completed feedback and the record becomes student viewed', async ({ page }) => {
    const { suffix, submissionId } = await prepareScenarioData();
    await loginAs(page, 'student01');

    await page.goto('/student-report-results');
    await expect(page.getByRole('heading', { name: '我的批阅结果' })).toBeVisible();
    const row = page.getByRole('listitem').filter({ hasText: `student-result-e2e-report-${suffix}` });
    await expect(row).toContainText('review_completed_feedback');
    await row.getByRole('link', { name: '查看详情' }).click();

    await expect(page).toHaveURL(new RegExp(`/student-report-results/${submissionId}$`));
    await expect(page.getByRole('heading', { name: `student-result-e2e-report-${suffix}` })).toBeVisible();
    await expect(page.getByText('状态：student_viewed_feedback')).toBeVisible();
    await expect(page.getByText(`请补充该 finding 的定位依据 ${suffix}`)).toBeVisible();
    await expect(page.getByText(`整体评价：批阅完成 ${suffix}`)).toBeVisible();
    await expect(page.getByText(`整改建议：下一轮提交前逐条回复批注 ${suffix}`)).toBeVisible();
    await expect(page.getByRole('list', { name: '历史轮次' })).toContainText(`student-result-history-${suffix}`);

    await expect.poll(() => readSubmissionStatus(submissionId)).toBe('student_viewed_feedback');
  });
});
