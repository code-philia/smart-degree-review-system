const { test, expect } = require('@playwright/test');
const { get, run } = require('../src/database');

const REQ_ID = 'FEAT-REPORT-SUPERVISOR-REVIEW';
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

async function ensureSupervisorReviewUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'supervisor02', 'supervisor02', password_hash, 'SUPERVISOR', 'college01', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'supervisor01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor02', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
}

async function clearSupervisorReviewData() {
  await run('DELETE FROM supervisor_review_feedback');
  await run('DELETE FROM in_app_todos');
  await run('DELETE FROM report_submissions');
}

async function seedReviewTodo(overrides = {}) {
  const submissionId = overrides.submission_id || `${overrides.todo_id}-submission`;
  await run(
    `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      submissionId,
      overrides.batch_id || `${submissionId}-batch`,
      overrides.student_id || 'student01',
      overrides.supervisor_id || overrides.assignee_id || 'supervisor01',
      overrides.source_type || 'normative',
      overrides.report_id || `${submissionId}-report`,
      overrides.submission_status || 'submitted_pending_review',
      overrides.submission_created_at || overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
  await run(
    `INSERT INTO in_app_todos (id, submission_id, assignee_id, actor_id, status, title, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      overrides.todo_id,
      submissionId,
      overrides.assignee_id || 'supervisor01',
      overrides.actor_id || overrides.student_id || 'student01',
      overrides.todo_status || 'pending',
      overrides.title || '报告待批阅',
      overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
  return submissionId;
}

async function prepareScenarioData() {
  await ensureSupervisorReviewUsers();
  await clearSupervisorReviewData();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const assignedSubmissionId = await seedReviewTodo({
    todo_id: `review-e2e-supervisor01-pending-${suffix}`,
    report_id: `review-e2e-assigned-report-${suffix}`,
    assignee_id: 'supervisor01',
    student_id: 'student01',
    title: 'supervisor01 在线批阅待办',
    created_at: '2026-08-05T12:00:00.000Z',
  });
  const foreignSubmissionId = await seedReviewTodo({
    todo_id: `review-e2e-supervisor02-foreign-${suffix}`,
    report_id: `review-e2e-foreign-report-${suffix}`,
    assignee_id: 'supervisor02',
    supervisor_id: 'supervisor02',
    student_id: 'student02',
    actor_id: 'student02',
    title: 'supervisor02 外部批阅待办',
    created_at: '2026-08-05T13:00:00.000Z',
  });
  return { suffix, assignedSubmissionId, foreignSubmissionId };
}

async function readSubmissionState(submissionId) {
  return get(
    `SELECT submission.status AS submission_status, todo.status AS todo_status
       FROM report_submissions AS submission
       INNER JOIN in_app_todos AS todo ON todo.submission_id = submission.id
      WHERE submission.id = ?`,
    [submissionId],
  );
}

test.describe('FEAT-REPORT-SUPERVISOR-REVIEW scenarios', () => {
  test('FEAT-REPORT-SUPERVISOR-REVIEW:E2E:SCENARIO:001 supervisor01 completes this review round and sees locked feedback', async ({ page }) => {
    const { suffix, assignedSubmissionId } = await prepareScenarioData();
    await loginAs(page, 'supervisor01');

    await page.goto('/supervisor-review-queue');
    await expect(page.getByRole('heading', { name: '待批阅任务' })).toBeVisible();
    const row = page.getByRole('row').filter({ hasText: `review-e2e-assigned-report-${suffix}` });
    await expect(row).toContainText('待批阅');
    await row.getByRole('link', { name: '批阅' }).click();

    await expect(page).toHaveURL(new RegExp(`/supervisor-review-queue/${assignedSubmissionId}$`));
    await expect(page.getByRole('heading', { name: '原报告批注与整体反馈' })).toBeVisible();
    await expect(page.getByText(`报告 review-e2e-assigned-report-${suffix}`)).toBeVisible();

    await page.getByLabel('finding_id').fill('finding-001');
    await page.getByLabel('批注内容').fill('请补充该 finding 的定位依据。');
    await page.getByRole('button', { name: '添加批注' }).click();
    await expect(page.getByText('请补充该 finding 的定位依据。')).toBeVisible();

    await page.getByLabel('整体评价（必填）').fill('整体评价：本轮批阅完成，请按批注进行整改。');
    await page.getByLabel('整改建议').fill('整改建议：下一轮提交前逐条回复导师批注。');
    await page.getByRole('button', { name: '提交评阅' }).click();

    await expect(page.getByText('已锁定')).toBeVisible();
    await expect(page.getByRole('button', { name: '提交评阅' })).toBeDisabled();
    await expect(page.getByLabel('整体评价（必填）')).toBeDisabled();

    const state = await readSubmissionState(assignedSubmissionId);
    expect(state).toEqual({ submission_status: 'review_completed_feedback', todo_status: 'done' });
    const feedback = await get('SELECT annotations_json, overall_evaluation, improvement_suggestions FROM supervisor_review_feedback WHERE submission_id = ?', [assignedSubmissionId]);
    expect(JSON.parse(feedback.annotations_json)).toEqual([{ finding_id: 'finding-001', comment: '请补充该 finding 的定位依据。' }]);
    expect(feedback.overall_evaluation).toBe('整体评价：本轮批阅完成，请按批注进行整改。');
    expect(feedback.improvement_suggestions).toBe('整改建议：下一轮提交前逐条回复导师批注。');

    await page.goto('/supervisor-review-queue');
    const completedRow = page.getByRole('row').filter({ hasText: `review-e2e-assigned-report-${suffix}` });
    await expect(completedRow).toContainText('已完成');
    await expect(completedRow.getByRole('link', { name: '查看记录' })).toHaveAttribute('href', `/supervisor-review-queue/${assignedSubmissionId}`);
  });

  test('FEAT-REPORT-SUPERVISOR-REVIEW:E2E:SCENARIO:002 supervisor01 is refused when the submission assignee is another supervisor', async ({ page }) => {
    const { foreignSubmissionId } = await prepareScenarioData();
    await loginAs(page, 'supervisor01');

    const readResponse = await page.request.get(`/api/normative/supervisor-review-queue/${foreignSubmissionId}`);
    expect(readResponse.status()).toBe(403);
    const readBody = await readResponse.json();
    expect(readBody.report).toBeUndefined();
    expect(JSON.stringify(readBody)).not.toContain('review-e2e-foreign-report');

    const submitResponse = await page.request.post(`/api/normative/supervisor-review-queue/${foreignSubmissionId}/review`, {
      data: {
        annotations: [{ finding_id: 'finding-foreign', comment: '不应写入' }],
        overall_evaluation: '不应允许非所属导师批阅',
      },
    });
    expect(submitResponse.status()).toBe(403);

    const feedback = await get('SELECT id FROM supervisor_review_feedback WHERE submission_id = ?', [foreignSubmissionId]);
    const state = await readSubmissionState(foreignSubmissionId);
    expect(feedback).toBeNull();
    expect(state).toEqual({ submission_status: 'submitted_pending_review', todo_status: 'pending' });
  });
});
