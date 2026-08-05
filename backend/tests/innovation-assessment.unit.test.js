import { describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const assessmentService = require('../src/normative/innovationAssessmentService');

const {
  ALLOWED_INNOVATION_ASSESSMENT_ROLES,
  INNOVATION_ASSESSMENT_DIMENSIONS,
  INNOVATION_ASSESSMENT_DISCLAIMER,
  MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH,
  createInnovationAssessment,
} = assessmentService;

const REQ_ID = 'FEAT-INNOVATION-ANALYZE';
void REQ_ID;

const studentUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
};

function longText(label) {
  return `${label}证据内容完整覆盖论文创新评估要求，长度超过二十个字符。`;
}

function validAssessmentPayload(overrides = {}) {
  const payload = {
    thesis_title: '高校数字治理创新机制研究',
    degree_type: 'master',
    primary_discipline: '管理学',
    secondary_discipline: '公共管理',
    research_direction: '高校数字治理',
    dimensions: Object.fromEntries(
      INNOVATION_ASSESSMENT_DIMENSIONS.map((dimension, index) => [
        dimension.key,
        {
          level: [5, 4, 4, 3, 4][index],
          evidence: longText(`${dimension.label}`),
          improvement_plan: `${dimension.label}改进计划将结合更多案例和数据验证，持续完善研究设计。`,
        },
      ]),
    ),
  };

  return {
    ...payload,
    ...overrides,
    dimensions: {
      ...payload.dimensions,
      ...(overrides.dimensions || {}),
    },
  };
}

describe('FEAT-INNOVATION-ANALYZE service validation and snapshot contract', () => {
  it('FEAT-INNOVATION-ANALYZE:UNIT:SCENARIO:001 persists normalized input, scoring details, total score, grade, and disclaimer', async () => {
    const payload = validAssessmentPayload();

    const result = await createInnovationAssessment(studentUser, payload);

    expect(result).toMatchObject({
      id: expect.any(String),
      user_id: 'student01',
      thesis_title: payload.thesis_title,
      degree_type: 'master',
      primary_discipline: payload.primary_discipline,
      secondary_discipline: payload.secondary_discipline,
      research_direction: payload.research_direction,
      total_score: 80,
      grade_label: '良好',
      disclaimer: INNOVATION_ASSESSMENT_DISCLAIMER,
      created_at: expect.any(String),
    });
    expect(result.input_snapshot).toEqual(payload);
    expect(result.input_snapshot.dimensions.research_method.evidence).toContain('研究方法');
    expect(result.input_snapshot.dimensions.research_method.improvement_plan).toContain('改进计划');
    expect(result.scoring_snapshot).toMatchObject({
      degree_type: 'master',
      total_score: 80,
      grade_label: '良好',
      input: {
        degree_type: 'master',
        levels: {
          research_topic: 5,
          research_method: 4,
          research_content: 4,
          research_conclusion: 3,
          application_value: 4,
        },
      },
    });
    expect(result.scoring_snapshot.formula).toContain('综合分=各维度原始分×权重之和');
    expect(result.scoring_snapshot.dimensions).toEqual([
      expect.objectContaining({ key: 'research_topic', level: 5, weight: 0.2, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_method', level: 4, weight: 0.2, weighted_score: 16 }),
      expect.objectContaining({ key: 'research_content', level: 4, weight: 0.25, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_conclusion', level: 3, weight: 0.2, weighted_score: 12 }),
      expect.objectContaining({ key: 'application_value', level: 4, weight: 0.15, weighted_score: 12 }),
    ]);
  });

  it('FEAT-INNOVATION-ANALYZE:UNIT:SCENARIO:002 rejects research method evidence shorter than 20 characters before persistence', async () => {
    const payload = validAssessmentPayload({
      dimensions: {
        research_method: {
          level: 4,
          evidence: '证据不足',
          improvement_plan: '研究方法改进计划将补充访谈设计和样本说明，确保可复核。',
        },
      },
    });

    await expect(createInnovationAssessment(studentUser, payload)).rejects.toMatchObject({
      status: 400,
      errors: [
        expect.objectContaining({
          field: 'dimensions.research_method.evidence',
          message: expect.stringContaining('研究方法证据'),
        }),
      ],
    });
  });

  it('FEAT-INNOVATION-ANALYZE:UNIT:VALIDATION:001 rejects missing scalar fields and out-of-range or incomplete dimensions', async () => {
    await expect(createInnovationAssessment(studentUser, validAssessmentPayload({ thesis_title: '   ' })))
      .rejects.toMatchObject({
        status: 400,
        errors: [expect.objectContaining({ field: 'thesis_title' })],
      });

    await expect(createInnovationAssessment(studentUser, validAssessmentPayload({
      dimensions: {
        application_value: {
          level: 6,
          evidence: longText('应用价值'),
          improvement_plan: longText('应用价值改进计划'),
        },
      },
    }))).rejects.toMatchObject({
      status: 400,
      errors: [expect.objectContaining({ field: 'dimensions.application_value.level' })],
    });

    const incomplete = validAssessmentPayload();
    delete incomplete.dimensions.research_conclusion;
    await expect(createInnovationAssessment(studentUser, incomplete)).rejects.toMatchObject({
      status: 400,
      errors: [expect.objectContaining({ field: 'dimensions.research_conclusion' })],
    });
  });

  it('FEAT-INNOVATION-ANALYZE:UNIT:AUTHZ:001 keeps defense-in-depth role checks aligned with the permission contract', async () => {
    expect(ALLOWED_INNOVATION_ASSESSMENT_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
    expect(MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH).toBe(20);

    await expect(createInnovationAssessment(null, validAssessmentPayload())).rejects.toMatchObject({ status: 401 });
    await expect(createInnovationAssessment({ ...studentUser, role: 'GUEST' }, validAssessmentPayload()))
      .rejects.toMatchObject({ status: 403 });
  });
});
