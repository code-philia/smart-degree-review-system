import { describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const historyService = require('../src/normative/aiReviewHistoryService');
const resultService = require('../src/normative/aiReviewResultService');
const repository = require('../src/normative/aiReviewRunRepository');

const {
  ALLOWED_AI_REVIEW_HISTORY_ROLES,
  listAiReviewHistoryForUser,
  toAiReviewHistoryRecord,
} = historyService;

const REQ_ID = 'FEAT-AI-REVIEW-HISTORY';
void REQ_ID;

const studentUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const persistedRuns = [
  {
    id: 'review-history-newest',
    user_id: 'student01',
    thesis_title: '新近辅助评阅论文',
    template_id: 'academic_master',
    source_type: 'paste',
    source_filename: null,
    original_text: '摘要\n关键词\n结论',
    section_snapshot: [{ name: '结论', present: true }],
    reference_count: 50,
    character_count: 8,
    normative_issues: [],
    score_items: [{ key: 'conclusion_section', label: '结论章节', points: 20, score: 20, findings: [] }],
    total_score: 90,
    result_label: '基础检查通过',
    missing_sections: [],
    rubric_snapshot: { template: { template_id: 'academic_master', name: '学术型硕士' } },
    created_at: '2026-03-02T10:00:00.000Z',
  },
  {
    id: 'review-history-older',
    user_id: 'student01',
    thesis_title: '较早辅助评阅论文',
    template_id: 'professional_master',
    source_type: 'file',
    source_filename: 'paper.md',
    original_text: '摘要\n关键词',
    section_snapshot: [{ name: '结论', present: false }],
    reference_count: 10,
    character_count: 5,
    normative_issues: [{ message: '缺少结论' }],
    score_items: [{ key: 'conclusion_section', label: '结论章节', points: 20, score: 0, findings: ['缺少结论章节'] }],
    total_score: 40,
    result_label: '需修改',
    missing_sections: ['结论'],
    rubric_snapshot: { template: { template_id: 'professional_master', name: '专业型硕士' } },
    created_at: '2026-03-01T09:00:00.000Z',
  },
];

describe('FEAT-AI-REVIEW-HISTORY service authorization and projection contract', () => {
  it('FEAT-AI-REVIEW-HISTORY:UNIT:AUTHZ:001 keeps history role access aligned with result viewing roles', () => {
    expect(ALLOWED_AI_REVIEW_HISTORY_ROLES).toEqual(resultService.ALLOWED_AI_REVIEW_RESULT_ROLES);
    expect(ALLOWED_AI_REVIEW_HISTORY_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
  });

  it('FEAT-AI-REVIEW-HISTORY:UNIT:AUTHZ:002 rejects missing and disallowed users before owner-scoped lookup', async () => {
    const lookupSpy = vi.spyOn(repository, 'listAiReviewRunsForUser');

    await expect(listAiReviewHistoryForUser(null)).rejects.toMatchObject({ status: 401 });
    await expect(listAiReviewHistoryForUser({ id: 'guest01', username: 'guest01', role: 'GUEST' }))
      .rejects.toMatchObject({ status: 403 });

    expect(lookupSpy).not.toHaveBeenCalled();
    lookupSpy.mockRestore();
  });

  it('FEAT-AI-REVIEW-HISTORY:UNIT:SCENARIO:001 lists current user runs through repository order and projects only history fields', async () => {
    const lookupSpy = vi.spyOn(repository, 'listAiReviewRunsForUser').mockResolvedValueOnce(persistedRuns);

    const records = await listAiReviewHistoryForUser(studentUser);

    expect(lookupSpy).toHaveBeenCalledWith('student01');
    expect(records).toEqual(persistedRuns.map(toAiReviewHistoryRecord));
    expect(records).toEqual([
      {
        id: 'review-history-newest',
        user_id: 'student01',
        thesis_title: '新近辅助评阅论文',
        template_id: 'academic_master',
        total_score: 90,
        result_label: '基础检查通过',
        created_at: '2026-03-02T10:00:00.000Z',
      },
      {
        id: 'review-history-older',
        user_id: 'student01',
        thesis_title: '较早辅助评阅论文',
        template_id: 'professional_master',
        total_score: 40,
        result_label: '需修改',
        created_at: '2026-03-01T09:00:00.000Z',
      },
    ]);
    expect(records[0]).not.toHaveProperty('original_text');
    expect(records[0]).not.toHaveProperty('score_items');
    expect(records[0]).not.toHaveProperty('rubric_snapshot');

    lookupSpy.mockRestore();
  });
});
