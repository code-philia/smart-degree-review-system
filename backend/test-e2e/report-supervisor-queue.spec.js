const { test, expect } = require('@playwright/test');
const { run } = require('../src/database');

const REQ_ID = 'FEAT-REPORT-SUPERVISOR-QUEUE';
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

async function ensureSupervisorQueueUsers() {
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

async function clearSupervisorQueueData() {
  await run('DELETE FROM in_app_todos');
  await run('DELETE FROM report_submissions');
}

async function seedQueueTodo(overrides = {}) {
  const submissionId = overrides.submission_id || `${overrides.todo_id}-submission`;
  await run(
    `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, 'submitted_pending_review', ?)`,
    [
      submissionId,
      overrides.batch_id || `${submissionId}-batch`,
      overrides.student_id || 'student01',
      overrides.supervisor_id || overrides.assignee_id || 'supervisor01',
      overrides.source_type || 'normative',
      overrides.report_id || `${submissionId}-report`,
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
      overrides.status || 'pending',
      overrides.title || '报告待批阅',
      overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
}

async function prepareScenarioData() {
  await ensureSupervisorQueueUsers();
  await clearSupervisorQueueData();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  await seedQueueTodo({
    todo_id: `queue-e2e-supervisor01-pending-${suffix}`,
    report_id: `normative-supervisor01-${suffix}`,
    assignee_id: 'supervisor01',
    student_id: 'student01',
    source_type: 'normative',
    status: 'pending',
    title: 'supervisor01 规范报告待批阅',
    created_at: '2026-08-05T12:00:00.000Z',
  });
  await seedQueueTodo({
    todo_id: `queue-e2e-supervisor01-done-${suffix}`,
    report_id: `ai-review-supervisor01-${suffix}`,
    assignee_id: 'supervisor01',
    student_id: 'student01',
    source_type: 'ai_review',
    status: 'done',
    title: 'supervisor01 AI 评阅已完成',
    created_at: '2026-08-05T11:00:00.000Z',
  });
  await seedQueueTodo({
    todo_id: `queue-e2e-supervisor02-foreign-${suffix}`,
    report_id: `normative-supervisor02-${suffix}`,
    assignee_id: 'supervisor02',
    supervisor_id: 'supervisor02',
    student_id: 'student02',
    actor_id: 'student02',
    source_type: 'normative',
    status: 'pending',
    title: 'supervisor02 外部报告待批阅',
    created_at: '2026-08-05T13:00:00.000Z',
  });
  return suffix;
}

test.describe('FEAT-REPORT-SUPERVISOR-QUEUE scenario', () => {
  test('FEAT-REPORT-SUPERVISOR-QUEUE:E2E:SCENARIO:001 supervisor01 sees only assigned queue rows and unread count', async ({ page }) => {
    const suffix = await prepareScenarioData();
    await loginAs(page, 'supervisor01');

    await page.goto('/supervisor-review-queue');
    await expect(page.getByRole('heading', { name: '待批阅任务' })).toBeVisible();
    await expect(page.getByText('未完成待办').locator('..')).toContainText('1');

    const table = page.getByRole('table');
    await expect(table).toContainText(`normative-supervisor01-${suffix}`);
    await expect(table).toContainText(`ai-review-supervisor01-${suffix}`);
    await expect(table).toContainText('student01');
    await expect(table).not.toContainText(`normative-supervisor02-${suffix}`);
    await expect(table).not.toContainText('student02');

    const rows = table.getByRole('row');
    await expect(rows.nth(1)).toContainText(`normative-supervisor01-${suffix}`);
    await expect(rows.nth(1)).toContainText('待批阅');
    await expect(rows.nth(2)).toContainText(`ai-review-supervisor01-${suffix}`);
    await expect(rows.nth(2)).toContainText('已完成');

    const queueResponse = await page.request.get('/api/normative/supervisor-review-queue');
    expect(queueResponse.status()).toBe(200);
    const body = await queueResponse.json();
    expect(body.unread_count).toBe(1);
    expect(body.records.map((record) => record.report_id)).toEqual([
      `normative-supervisor01-${suffix}`,
      `ai-review-supervisor01-${suffix}`,
    ]);
    expect(JSON.stringify(body)).not.toContain(`normative-supervisor02-${suffix}`);
  });
});
