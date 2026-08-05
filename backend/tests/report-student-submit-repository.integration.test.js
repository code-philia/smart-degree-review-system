import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, get, run } = require('../src/database');
const { createReportSubmissionBatch } = require('../src/normative/reportSubmissionRepository');

const REQ_ID = 'FEAT-REPORT-STUDENT-SUBMIT';
void REQ_ID;

let harness;

function reportDescriptor(overrides = {}) {
  return {
    submission_id: overrides.submission_id || 'submission-repository-001',
    todo_id: overrides.todo_id || 'todo-repository-001',
    source_type: overrides.source_type || 'normative',
    report_id: overrides.report_id || 'normative-repository-001',
    todo_title: overrides.todo_title || '报告待批阅',
  };
}

describe('FEAT-REPORT-STUDENT-SUBMIT repository and schema contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-report-student-submit-repository', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM in_app_todos');
    await run('DELETE FROM report_submissions');
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:DB:SCHEMA:001 initializes constrained report_submissions and in_app_todos tables', async () => {
    const submissionTable = await get("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'report_submissions'");
    const todoTable = await get("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'in_app_todos'");
    expect(submissionTable).toEqual({ name: 'report_submissions' });
    expect(todoTable).toEqual({ name: 'in_app_todos' });

    await expect(run(
      `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      ['invalid-source-submission', 'batch-invalid', 'student01', 'supervisor01', 'unsupported', 'r1', 'submitted_pending_review'],
    )).rejects.toThrow(/CHECK constraint failed/);

    await expect(run(
      `INSERT INTO in_app_todos (id, submission_id, assignee_id, actor_id, status, title)
       VALUES (?, ?, ?, ?, ?, ?)`,
      ['orphan-todo', 'missing-submission', 'supervisor01', 'student01', 'pending', '报告待批阅'],
    )).rejects.toThrow(/FOREIGN KEY constraint failed/);
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:DB:REPOSITORY:001 atomically inserts one submission and one supervisor todo per selected report', async () => {
    const response = await createReportSubmissionBatch({
      batchId: 'batch-repository-001',
      studentId: 'student01',
      supervisorId: 'supervisor01',
      createdAt: '2026-08-05T10:00:00.000Z',
      reports: [
        reportDescriptor({ submission_id: 'submission-repository-001', todo_id: 'todo-repository-001', report_id: 'normative-repository-001' }),
        reportDescriptor({ submission_id: 'submission-repository-002', todo_id: 'todo-repository-002', source_type: 'ai_review', report_id: 'ai-review-repository-001' }),
      ],
    });

    expect(response.batch_id).toBe('batch-repository-001');
    expect(response.submissions).toHaveLength(2);
    expect(response.todos).toHaveLength(2);
    expect(response.submissions.map((submission) => submission.status)).toEqual(['submitted_pending_review', 'submitted_pending_review']);
    expect(response.todos.map((todo) => todo.assignee_id)).toEqual(['supervisor01', 'supervisor01']);

    const persistedCounts = await get(
      `SELECT
         (SELECT COUNT(*) FROM report_submissions WHERE batch_id = ?) AS submissions,
         (SELECT COUNT(*) FROM in_app_todos WHERE assignee_id = ?) AS todos`,
      ['batch-repository-001', 'supervisor01'],
    );
    expect(persistedCounts).toEqual({ submissions: 2, todos: 2 });
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:DB:REPOSITORY:002 rolls back the whole batch when any todo write fails', async () => {
    await expect(createReportSubmissionBatch({
      batchId: 'batch-repository-rollback',
      studentId: 'student01',
      supervisorId: 'missing-supervisor',
      createdAt: '2026-08-05T11:00:00.000Z',
      reports: [reportDescriptor({ submission_id: 'submission-rollback-001', todo_id: 'todo-rollback-001' })],
    })).rejects.toThrow(/FOREIGN KEY constraint failed/);

    const persistedCounts = await get(
      `SELECT
         (SELECT COUNT(*) FROM report_submissions WHERE batch_id = ?) AS submissions,
         (SELECT COUNT(*) FROM in_app_todos WHERE id = ?) AS todos`,
      ['batch-repository-rollback', 'todo-rollback-001'],
    );
    expect(persistedCounts).toEqual({ submissions: 0, todos: 0 });
  });
});
