import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, get } = require('../src/database');
const {
  insertAiReviewRun,
  findAiReviewRunForUser,
  listAiReviewRunsForUser,
} = require('../src/normative/aiReviewRunRepository');

const REQ_ID = 'FEAT-AI-REVIEW-RUN';
void REQ_ID;

let harness;

function reviewRunFixture(overrides = {}) {
  return {
    id: 'review-run-fixture-001',
    user_id: 'student01',
    thesis_title: '高校数字治理平台评阅研究',
    template_id: 'academic_master',
    source_type: 'paste',
    source_filename: null,
    original_text: '摘要\n关键词\n引言\n研究方法\n分析与讨论\n参考文献\n[1] 引用条目 1',
    section_snapshot: [
      { name: '摘要', present: true },
      { name: '结论', present: false },
      { name: '参考文献', present: true },
    ],
    reference_count: 1,
    character_count: 29,
    normative_issues: [
      { rule_id: 'NORM-001', category: '章节顺序', severity: 'high', line: 6, column: 1, excerpt: '结论', message: '缺少必需章节：结论', suggestion: '补充“结论”并按规定顺序排列' },
    ],
    score_items: [
      { key: 'section_completeness', label: '章节完整性', points: 30, score: 0, findings: ['结论'] },
      { key: 'conclusion_section', label: '结论章节', points: 20, score: 0, findings: ['缺少结论章节'] },
    ],
    total_score: 40,
    result_label: '需修改',
    missing_sections: ['结论'],
    rubric_snapshot: {
      template: { template_id: 'academic_master', name: '学术型硕士', required_sections: ['摘要', '关键词', '引言', '研究方法', '分析与讨论', '结论', '参考文献'], minimum_reference_count: 50 },
      shared_score_items: [],
      passing_rule: { minimum_objective_score: 80, no_required_section_missing: true, pass_label: '基础检查通过', revise_label: '需修改' },
    },
    created_at: '2026-01-01T00:00:00.000Z',
    ...overrides,
  };
}

describe('FEAT-AI-REVIEW-RUN repository persistence contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ai-review-run-repository', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('creates the ai_review_runs table in the isolated test database', async () => {
    const table = await get("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_review_runs'");
    expect(table).toEqual({ name: 'ai_review_runs' });
  });

  it('inserts parsed JSON snapshots and keeps lookups owner-scoped', async () => {
    const reviewRun = reviewRunFixture();

    const inserted = await insertAiReviewRun(reviewRun);
    expect(inserted).toEqual(reviewRun);

    const owned = await findAiReviewRunForUser(reviewRun.id, 'student01');
    expect(owned).toMatchObject({
      id: reviewRun.id,
      user_id: 'student01',
      thesis_title: '高校数字治理平台评阅研究',
      missing_sections: ['结论'],
      result_label: '需修改',
    });
    expect(owned.section_snapshot).toEqual(reviewRun.section_snapshot);
    expect(owned.score_items).toEqual(reviewRun.score_items);
    expect(owned.rubric_snapshot.template.template_id).toBe('academic_master');

    const otherUser = await findAiReviewRunForUser(reviewRun.id, 'supervisor01');
    expect(otherUser).toBeNull();

    const ownedList = await listAiReviewRunsForUser('student01');
    expect(ownedList).toHaveLength(1);
    expect(ownedList[0].id).toBe(reviewRun.id);
    expect(ownedList[0].missing_sections).toEqual(['结论']);
  });
});
