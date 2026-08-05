import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const reportService = require('../src/normative/innovationReportService');

const {
  ALLOWED_INNOVATION_REPORT_ROLES,
  buildInnovationReportDownloadPayload,
  getInnovationReportForUser,
} = reportService;

const REQ_ID = 'FEAT-INNOVATION-REPORT';
void REQ_ID;

const report = {
  id: 'report-001',
  user_id: 'student01',
  thesis_title: '高校数字治理创新机制研究',
  total_score: 80,
  grade_label: '良好',
  formula: '维度原始分=等级×20；综合分=各维度原始分×权重之和。',
  dimensions: [
    { key: 'research_method', label: '研究方法', level: 4, weight: 0.2, weighted_score: 16 },
  ],
  input_snapshot: {
    thesis_title: '高校数字治理创新机制研究',
    dimensions: {
      research_method: {
        level: 4,
        evidence: '研究方法证据围绕资料来源和可验证路径展开。',
        improvement_plan: '研究方法改进计划将增加访谈样本和三角验证。',
      },
    },
  },
  scoring_snapshot: {
    total_score: 80,
    grade_label: '良好',
    dimensions: [
      { key: 'research_method', label: '研究方法', level: 4, weight: 0.2, weighted_score: 16 },
    ],
  },
  disclaimer: '本结果为量表自评，不代替专家评审或文献查新',
  created_at: '2026-01-01T00:00:00.000Z',
};

describe('FEAT-INNOVATION-REPORT service authorization and payload consistency', () => {
  it('FEAT-INNOVATION-REPORT:UNIT:AUTHZ:001 keeps the report role allow-list aligned with declared ALL role access', () => {
    expect(ALLOWED_INNOVATION_REPORT_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
  });

  it('FEAT-INNOVATION-REPORT:UNIT:AUTHZ:002 rejects missing or disallowed users before report retrieval can return data', async () => {
    await expect(getInnovationReportForUser(null, 'report-001')).rejects.toMatchObject({ status: 401 });
    await expect(getInnovationReportForUser({ id: 'guest01', username: 'guest01', role: 'GUEST' }, 'report-001'))
      .rejects.toMatchObject({ status: 403 });
  });

  it('FEAT-INNOVATION-REPORT:UNIT:DOWNLOAD:001 builds JSON download payload from the exact fetched report values', () => {
    const payload = buildInnovationReportDownloadPayload(report);

    expect(payload).toMatchObject({
      id: report.id,
      thesis_title: report.thesis_title,
      total_score: report.total_score,
      grade_label: report.grade_label,
      formula: report.formula,
      dimensions: report.dimensions,
      input_snapshot: report.input_snapshot,
      scoring_snapshot: report.scoring_snapshot,
      disclaimer: report.disclaimer,
      exported_at: expect.any(String),
    });
    expect(payload.dimensions).toEqual(report.scoring_snapshot.dimensions);
    expect(payload.total_score).toBe(report.scoring_snapshot.total_score);
    expect(payload.grade_label).toBe(report.scoring_snapshot.grade_label);
  });
});
