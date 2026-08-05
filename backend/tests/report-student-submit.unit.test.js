import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const service = require('../src/normative/reportSubmissionService');
const repository = require('../src/normative/reportSubmissionRepository');

const REQ_ID = 'FEAT-REPORT-STUDENT-SUBMIT';
void REQ_ID;

const studentUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  supervisor_id: 'supervisor01',
  scope: 'COLLEGE',
};

describe('FEAT-REPORT-STUDENT-SUBMIT service validation and orchestration contract', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:UNIT:AUTHZ:001 exposes STUDENT-only access and rejects missing, wrong-role, and unbound actors before persistence', async () => {
    expect(service.ALLOWED_REPORT_SUBMISSION_ROLES).toEqual(['STUDENT']);
    expect(service.REPORT_SUBMISSION_SOURCE_TYPES).toEqual(['normative', 'duplication', 'innovation', 'ai_review']);
    const writeSpy = vi.spyOn(repository, 'createReportSubmissionBatch');

    expect(() => service.ensureStudentSubmissionActor(null)).toThrow(/登录/);
    expect(() => service.ensureStudentSubmissionActor({ ...studentUser, role: 'SUPERVISOR' })).toThrow(/仅学生/);
    expect(() => service.ensureStudentSubmissionActor({ ...studentUser, supervisor_id: '', supervisorId: '' })).toThrow(/未绑定导师/);

    await expect(service.createReportSubmissionsForStudent(null, { reports: [] })).rejects.toMatchObject({ status: 401 });
    await expect(service.createReportSubmissionsForStudent({ ...studentUser, role: 'SCHOOL_ADMIN' }, { reports: [] }))
      .rejects.toMatchObject({ status: 403 });
    await expect(service.createReportSubmissionsForStudent({ ...studentUser, supervisor_id: '', supervisorId: '' }, { reports: [] }))
      .rejects.toMatchObject({ status: 400 });
    expect(writeSpy).not.toHaveBeenCalled();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:UNIT:VALIDATION:001 rejects empty and malformed report selections before repository writes', async () => {
    const writeSpy = vi.spyOn(repository, 'createReportSubmissionBatch');

    await expect(service.createReportSubmissionsForStudent(studentUser, {})).rejects.toMatchObject({ status: 400 });
    await expect(service.createReportSubmissionsForStudent(studentUser, { reports: [] })).rejects.toMatchObject({ status: 400 });
    await expect(service.createReportSubmissionsForStudent(studentUser, { reports: [{ source_type: 'unknown', report_id: 'r1' }] }))
      .rejects.toMatchObject({ status: 400 });
    await expect(service.createReportSubmissionsForStudent(studentUser, { reports: [{ source_type: 'normative', report_id: '   ' }] }))
      .rejects.toMatchObject({ status: 400 });

    expect(writeSpy).not.toHaveBeenCalled();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:UNIT:SCENARIO:001 delegates a verified batch with one generated submission and todo per selected report', async () => {
    const writeSpy = vi.spyOn(repository, 'createReportSubmissionBatch').mockImplementation(async (batch) => ({
      batch_id: batch.batchId,
      submissions: batch.reports.map((report) => ({
        id: report.submission_id,
        batch_id: batch.batchId,
        student_id: batch.studentId,
        supervisor_id: batch.supervisorId,
        source_type: report.source_type,
        report_id: report.report_id,
        status: 'submitted_pending_review',
        created_at: batch.createdAt,
      })),
      todos: batch.reports.map((report) => ({
        id: report.todo_id,
        submission_id: report.submission_id,
        assignee_id: batch.supervisorId,
        actor_id: batch.studentId,
        status: 'pending',
        title: report.todo_title,
        created_at: batch.createdAt,
      })),
    }));

    const response = await service.createReportSubmissionsForStudent(studentUser, {
      reports: [
        { source_type: 'normative', report_id: 'normative-owned-completed' },
        { source_type: 'ai_review', report_id: 'ai-review-owned-completed' },
      ],
    });

    expect(writeSpy).toHaveBeenCalledTimes(1);
    const batch = writeSpy.mock.calls[0][0];
    expect(batch).toMatchObject({
      batchId: expect.any(String),
      studentId: 'student01',
      supervisorId: 'supervisor01',
      createdAt: expect.any(String),
    });
    expect(batch.reports).toEqual([
      expect.objectContaining({
        source_type: 'normative',
        report_id: 'normative-owned-completed',
        submission_id: expect.any(String),
        todo_id: expect.any(String),
        todo_title: expect.stringMatching(/报告|批阅/),
      }),
      expect.objectContaining({
        source_type: 'ai_review',
        report_id: 'ai-review-owned-completed',
        submission_id: expect.any(String),
        todo_id: expect.any(String),
        todo_title: expect.stringMatching(/报告|批阅/),
      }),
    ]);
    expect(batch.reports[0].submission_id).not.toBe(batch.reports[1].submission_id);
    expect(batch.reports[0].todo_id).not.toBe(batch.reports[1].todo_id);
    expect(response.submissions).toHaveLength(2);
    expect(response.todos).toHaveLength(2);
  });
});
