import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createAiReviewRun, ALLOWED_AI_REVIEW_RUN_ROLES, ALLOWED_AI_REVIEW_FILE_EXTENSIONS, MAX_AI_REVIEW_TEXT_BYTES } = require('../src/normative/aiReviewRunService');
const { createTestDatabaseHarness, get } = require('../src/database');

const REQ_ID = 'FEAT-AI-REVIEW-RUN';
void REQ_ID;

const studentUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

let harness;

function buildReferenceLines(count) {
  return Array.from({ length: count }, (_, index) => `[${index + 1}] 引用条目 ${index + 1}`).join('\n');
}

function buildMissingConclusionText(referenceCount = 50) {
  return [
    '摘要',
    '关键词',
    '引言',
    '研究方法',
    '分析与讨论',
    '参考文献',
    buildReferenceLines(referenceCount),
  ].join('\n');
}

describe('FEAT-AI-REVIEW-RUN service review-run scoring contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ai-review-run-unit', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('rejects incomplete payloads, unknown templates, and unauthorized roles before persistence', async () => {
    expect(ALLOWED_AI_REVIEW_RUN_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
    expect(ALLOWED_AI_REVIEW_FILE_EXTENSIONS).toEqual(['.txt', '.md', '.pdf']);
    expect(MAX_AI_REVIEW_TEXT_BYTES).toBe(50 * 1024 * 1024);

    await expect(createAiReviewRun(null, {})).rejects.toMatchObject({ status: 401 });
    await expect(createAiReviewRun({ ...studentUser, role: 'GUEST' }, {
      thesis_title: '论文题目',
      template_id: 'academic_master',
      text: buildMissingConclusionText(),
      source_type: 'paste',
    })).rejects.toMatchObject({ status: 403 });

    await expect(createAiReviewRun(studentUser, {
      thesis_title: '   ',
      template_id: '',
      text: '   ',
      source_type: 'paste',
    })).rejects.toMatchObject({
      status: 400,
      errors: expect.arrayContaining([
        expect.objectContaining({ field: 'thesis_title' }),
        expect.objectContaining({ field: 'template_id' }),
        expect.objectContaining({ field: 'text' }),
      ]),
    });

    await expect(createAiReviewRun(studentUser, {
      thesis_title: '论文题目',
      template_id: 'not_a_template',
      text: buildMissingConclusionText(),
      source_type: 'paste',
    })).rejects.toMatchObject({
      status: 400,
      message: '评阅模板不存在',
    });
  });

  it('scores missing conclusion as 0 and marks the run for revision while preserving the persisted snapshot', async () => {
    const text = buildMissingConclusionText();
    const result = await createAiReviewRun(studentUser, {
      thesis_title: '高校数字治理平台评阅研究',
      template_id: 'academic_master',
      text,
      source_type: 'paste',
    });

    expect(result).toMatchObject({
      user_id: 'student01',
      thesis_title: '高校数字治理平台评阅研究',
      template_id: 'academic_master',
      source_type: 'paste',
      source_filename: null,
      original_text: text,
      reference_count: 50,
      result_label: '需修改',
      missing_sections: ['结论'],
      created_at: expect.any(String),
    });
    expect(result.character_count).toBe(Array.from(text).length);
    expect(result.section_snapshot).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: '结论', present: false }),
        expect.objectContaining({ name: '参考文献', present: true }),
      ]),
    );
    expect(result.score_items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'conclusion_section', score: 0, findings: ['缺少结论章节'] }),
      ]),
    );
    expect(result.normative_issues.some((issue) => issue.message.includes('缺少必需章节：结论'))).toBe(true);
    expect(result.rubric_snapshot.template.template_id).toBe('academic_master');
    expect(result.rubric_snapshot.passing_rule.revise_label).toBe('需修改');

    const persisted = await get('SELECT result_label, missing_sections_json AS missingSectionsJson, score_items_json AS scoreItemsJson FROM ai_review_runs WHERE id = ?', [result.id]);
    expect(persisted.result_label).toBe('需修改');
    expect(JSON.parse(persisted.missingSectionsJson)).toEqual(['结论']);
    expect(JSON.parse(persisted.scoreItemsJson)).toEqual(result.score_items);
  });
});
