import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const service = require('../src/normative/reportSupervisorQueueService');
const repository = require('../src/normative/reportSupervisorQueueRepository');

const REQ_ID = 'FEAT-REPORT-SUPERVISOR-QUEUE';
void REQ_ID;

const supervisorUser = {
  id: 'supervisor01',
  username: 'supervisor01',
  role: 'SUPERVISOR',
  collegeId: 'college01',
  scope: 'COLLEGE',
};

describe('FEAT-REPORT-SUPERVISOR-QUEUE service authorization and scoping contract', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:UNIT:AUTHZ:001 exposes SUPERVISOR-only access and rejects missing or denied actors before repository reads', async () => {
    expect(service.ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES).toEqual(['SUPERVISOR']);
    expect(service.REPORT_SUPERVISOR_QUEUE_STATUSES).toEqual(['pending', 'done']);
    const listSpy = vi.spyOn(repository, 'listSupervisorReviewTodos');
    const badgeSpy = vi.spyOn(repository, 'countIncompleteSupervisorReviewTodos');

    expect(() => service.ensureSupervisorQueueActor(null)).toThrow(/登录/);
    expect(() => service.ensureSupervisorQueueActor({ id: 'student01', username: 'student01', role: 'STUDENT' })).toThrow(/仅导师/);
    expect(() => service.ensureSupervisorQueueActor({ id: 'school_admin01', username: 'school_admin01', role: 'SCHOOL_ADMIN' })).toThrow(/仅导师/);
    expect(() => service.ensureSupervisorQueueActor({ id: 'college_admin01', username: 'college_admin01', role: 'COLLEGE_ADMIN' })).toThrow(/仅导师/);

    await expect(service.listSupervisorReviewQueue(null, {})).rejects.toMatchObject({ status: 401 });
    await expect(service.listSupervisorReviewQueue({ id: 'student01', username: 'student01', role: 'STUDENT' }, {}))
      .rejects.toMatchObject({ status: 403 });
    await expect(service.getSupervisorReviewQueueBadge({ id: 'college_admin01', username: 'college_admin01', role: 'COLLEGE_ADMIN' }))
      .rejects.toMatchObject({ status: 403 });

    expect(listSpy).not.toHaveBeenCalled();
    expect(badgeSpy).not.toHaveBeenCalled();
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:UNIT:SCENARIO:001 derives assignee scope from the current supervisor and normalizes only supported queue filters', async () => {
    const listSpy = vi.spyOn(repository, 'listSupervisorReviewTodos').mockResolvedValue({ records: [], unread_count: 0 });
    const badgeSpy = vi.spyOn(repository, 'countIncompleteSupervisorReviewTodos').mockResolvedValue({ unread_count: 2 });

    expect(service.normalizeSupervisorQueueFilters({
      student_id: ' student01 ',
      source_type: ' normative ',
      status: ' pending ',
      assignee_id: 'supervisor02',
      ignored: 'value',
    })).toEqual({ student_id: 'student01', source_type: 'normative', status: 'pending' });

    await service.listSupervisorReviewQueue(supervisorUser, {
      student_id: ' student01 ',
      source_type: ' normative ',
      status: ' pending ',
      assignee_id: 'supervisor02',
    });
    await service.getSupervisorReviewQueueBadge(supervisorUser);

    expect(listSpy).toHaveBeenCalledWith({
      supervisorId: 'supervisor01',
      filters: { student_id: 'student01', source_type: 'normative', status: 'pending' },
    });
    expect(badgeSpy).toHaveBeenCalledWith({ supervisorId: 'supervisor01' });
  });
});
