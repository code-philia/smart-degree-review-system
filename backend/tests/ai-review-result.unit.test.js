import { describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const resultService = require('../src/normative/aiReviewResultService');
const repository = require('../src/normative/aiReviewRunRepository');

const {
  ALLOWED_AI_REVIEW_RESULT_ROLES,
  SUBJECTIVE_CONFIRMATION_ITEMS,
  buildAiReviewResultDownloadPayload,
  getAiReviewResultForUser,
} = resultService;

const REQ_ID = 'FEAT-AI-REVIEW-RESULT';
void REQ_ID;

const studentUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const persistedRun = {
  id: 'review-run-result-001',
  user_id: 'student01',
  thesis_title: '辅助评阅结果验证论文',
  template_id: 'academic_master',
  source_type: 'paste',
  source_filename: null,
  original_text: '摘要\n关键词\n引言\n研究方法\n分析与讨论\n结论\n参考文献',
  section_snapshot: [
    { name: '摘要', present: true },
    { name: '结论', present: true },
  ],
  reference_count: 0,
  character_count: 31,
  normative_issues: [
    { rule_id: 'NORM-REF-COUNT', severity: 'medium', message: '参考文献数量不足', suggestion: '补充引用' },
  ],
  score_items: [
    { key: 'section_completeness', label: '章节完整性', points: 20, score: 20, findings: [] },
    { key: 'abstract_keywords', label: '摘要与关键词', points: 20, score: 20, findings: [] },
    { key: 'method_discussion', label: '方法与讨论', points: 20, score: 20, findings: [] },
    { key: 'conclusion_section', label: '结论章节', points: 20, score: 20, findings: [] },
    { key: 'references', label: '参考文献', points: 20, score: 10, findings: ['参考文献数量不足'] },
  ],
  total_score: 90,
  result_label: '基础检查通过',
  missing_sections: [],
  rubric_snapshot: {
    template: { template_id: 'academic_master', name: '学术型硕士' },
    passing_rule: { pass_label: '基础检查通过', revise_label: '需修改' },
  },
  created_at: '2026-01-01T00:00:00.000Z',
};

describe('FEAT-AI-REVIEW-RESULT service authorization and derived result contract', () => {
  it('FEAT-AI-REVIEW-RESULT:UNIT:AUTHZ:001 keeps the result role allow-list aligned with declared ALL role access', () => {
    expect(ALLOWED_AI_REVIEW_RESULT_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
  });

  it('FEAT-AI-REVIEW-RESULT:UNIT:AUTHZ:002 rejects missing and disallowed users before owner-scoped result lookup', async () => {
    const lookupSpy = vi.spyOn(repository, 'findAiReviewRunForUser');

    await expect(getAiReviewResultForUser(null, persistedRun.id)).rejects.toMatchObject({ status: 401 });
    await expect(getAiReviewResultForUser({ id: 'guest01', username: 'guest01', role: 'GUEST' }, persistedRun.id))
      .rejects.toMatchObject({ status: 403 });

    expect(lookupSpy).not.toHaveBeenCalled();
    lookupSpy.mockRestore();
  });

  it('FEAT-AI-REVIEW-RESULT:UNIT:SCORING:001 decorates an owned completed run with objective total and human-confirmation subjective dimensions', async () => {
    const lookupSpy = vi
      .spyOn(repository, 'findAiReviewRunForUser')
      .mockResolvedValueOnce(persistedRun);

    const result = await getAiReviewResultForUser(studentUser, persistedRun.id);

    expect(lookupSpy).toHaveBeenCalledWith(persistedRun.id, 'student01');
    expect(result).toMatchObject({
      id: persistedRun.id,
      user_id: 'student01',
      thesis_title: persistedRun.thesis_title,
      template_id: persistedRun.template_id,
      total_score: 90,
      result_label: '基础检查通过',
      normative_issues: persistedRun.normative_issues,
    });
    expect(result.score_items).toHaveLength(5);
    expect(result.objective_score_total).toBe(90);
    expect(result.objective_score_total).toBe(result.score_items.reduce((sum, item) => sum + item.score, 0));
    expect(result.subjective_confirmation_items).toEqual(SUBJECTIVE_CONFIRMATION_ITEMS);
    expect(result.subjective_confirmation_items.length).toBeGreaterThan(0);
    expect(result.subjective_confirmation_items.every((item) => item.status === '待人工确认')).toBe(true);

    lookupSpy.mockRestore();
  });

  it('FEAT-AI-REVIEW-RESULT:UNIT:DOWNLOAD:001 builds a JSON download envelope from the fetched result values', () => {
    const decoratedResult = {
      ...persistedRun,
      objective_score_total: 90,
      subjective_confirmation_items: SUBJECTIVE_CONFIRMATION_ITEMS,
    };

    const payload = buildAiReviewResultDownloadPayload(decoratedResult);

    expect(payload).toMatchObject({
      report_type: 'ai_review_result',
      generated_at: expect.any(String),
      result: decoratedResult,
    });
    expect(payload.result.score_items).toHaveLength(5);
    expect(payload.result.objective_score_total).toBe(payload.result.total_score);
    expect(payload.result.subjective_confirmation_items.every((item) => item.status === '待人工确认')).toBe(true);
  });
});
