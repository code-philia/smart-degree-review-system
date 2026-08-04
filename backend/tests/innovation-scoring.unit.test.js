import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  ALLOWED_INNOVATION_SCORING_ROLES,
  INNOVATION_SCORE_DIMENSIONS,
  INNOVATION_SCORE_WEIGHTS,
  calculateInnovationScore,
} = require('../src/normative/innovationScoringService');

const REQ_ID = 'FEAT-INNOVATION-SCORING-MODEL';
void REQ_ID;

const studentUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
};

function levels(researchTopic, researchMethod, researchContent, researchConclusion, applicationValue) {
  return {
    research_topic: researchTopic,
    research_method: researchMethod,
    research_content: researchContent,
    research_conclusion: researchConclusion,
    application_value: applicationValue,
  };
}

function request(degreeType, scoreLevels) {
  return {
    degree_type: degreeType,
    levels: scoreLevels,
  };
}

describe('FEAT-INNOVATION-SCORING-MODEL fixed transparent scoring service', () => {
  it('calculates the declared master scenario as 80 and 良好 with transparent dimension details', async () => {
    const payload = request('master', levels(5, 4, 4, 3, 4));

    const report = await calculateInnovationScore(studentUser, payload);

    expect(report).toMatchObject({
      degree_type: 'master',
      total_score: 80,
      grade_label: '良好',
      input: payload,
    });
    expect(report.formula).toContain('维度原始分=等级×20');
    expect(report.formula).toContain('综合分=各维度原始分×权重之和');
    expect(report.dimensions).toEqual([
      expect.objectContaining({ key: 'research_topic', level: 5, raw_score: 100, weight: 0.2, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_method', level: 4, raw_score: 80, weight: 0.2, weighted_score: 16 }),
      expect.objectContaining({ key: 'research_content', level: 4, raw_score: 80, weight: 0.25, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_conclusion', level: 3, raw_score: 60, weight: 0.2, weighted_score: 12 }),
      expect.objectContaining({ key: 'application_value', level: 4, raw_score: 80, weight: 0.15, weighted_score: 12 }),
    ]);
  });

  it('publishes the fixed dimensions and doctoral/master weights in requirement order', () => {
    expect(INNOVATION_SCORE_DIMENSIONS.map((dimension) => dimension.key)).toEqual([
      'research_topic',
      'research_method',
      'research_content',
      'research_conclusion',
      'application_value',
    ]);
    const dimensionKeys = INNOVATION_SCORE_DIMENSIONS.map((dimension) => dimension.key);
    expect(dimensionKeys.map((key) => INNOVATION_SCORE_WEIGHTS.doctoral[key])).toEqual([0.25, 0.25, 0.2, 0.2, 0.1]);
    expect(dimensionKeys.map((key) => INNOVATION_SCORE_WEIGHTS.master[key])).toEqual([0.2, 0.2, 0.25, 0.2, 0.15]);
  });

  it('classifies score boundaries at 90, 80, 60, and below 60', async () => {
    await expect(calculateInnovationScore(studentUser, request('master', levels(5, 5, 4, 5, 4))))
      .resolves.toMatchObject({ total_score: 92, grade_label: '优秀' });
    await expect(calculateInnovationScore(studentUser, request('master', levels(4, 4, 4, 4, 4))))
      .resolves.toMatchObject({ total_score: 80, grade_label: '良好' });
    await expect(calculateInnovationScore(studentUser, request('master', levels(3, 3, 3, 3, 3))))
      .resolves.toMatchObject({ total_score: 60, grade_label: '一般' });
    await expect(calculateInnovationScore(studentUser, request('master', levels(2, 3, 3, 3, 3))))
      .resolves.toMatchObject({ total_score: 56, grade_label: '待提升' });
  });

  it('rejects unauthenticated users, disallowed roles, invalid degree types, and missing or out-of-range levels', async () => {
    await expect(calculateInnovationScore(null, request('master', levels(5, 4, 4, 3, 4))))
      .rejects.toMatchObject({ status: 401 });
    await expect(calculateInnovationScore({ ...studentUser, role: 'GUEST' }, request('master', levels(5, 4, 4, 3, 4))))
      .rejects.toMatchObject({ status: 403 });
    await expect(calculateInnovationScore(studentUser, request('associate', levels(5, 4, 4, 3, 4))))
      .rejects.toMatchObject({ status: 400 });
    await expect(calculateInnovationScore(studentUser, request('master', { ...levels(5, 4, 4, 3, 4), application_value: 6 })))
      .rejects.toMatchObject({ status: 400 });
    await expect(calculateInnovationScore(studentUser, request('master', { research_topic: 5 })))
      .rejects.toMatchObject({ status: 400 });
  });

  it('allows all declared roles at the service authorization boundary', async () => {
    expect(ALLOWED_INNOVATION_SCORING_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

    for (const role of ALLOWED_INNOVATION_SCORING_ROLES) {
      await expect(calculateInnovationScore({ ...studentUser, role }, request('doctoral', levels(5, 5, 5, 5, 5))))
        .resolves.toMatchObject({ total_score: 100, grade_label: '优秀' });
    }
  });
});
