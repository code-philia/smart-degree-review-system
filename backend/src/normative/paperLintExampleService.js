const fs = require('fs');
const path = require('path');
const { resolveEngineBackendDir } = require('./reviewPilotPaperLintService');

const CLAIM_EVIDENCE_CASE_ID = 'yandex-accuracy-claim-evidence';
const PDF_FILENAME = '内置案例-论点与论据一致性.pdf';
const PDF_RELATIVE_PATH = path.join('novref', 'domain', 'examples', 'assets', 'sjtu-paper-lint-current-rules.pdf');

function pdfRect({ x1, y1, x2, y2, pageNumber }) {
  return {
    x1,
    y1,
    x2,
    y2,
    width: 595.280029296875,
    height: 841.8900146484375,
    page_number: pageNumber,
  };
}

const claimRect = pdfRect({
  x1: 94.86599731445312,
  y1: 648.8480224609375,
  x2: 518.4400024414062,
  y2: 661.7720336914062,
  pageNumber: 22,
});
const evidenceBoundingRect = pdfRect({
  x1: 85.03900146484375,
  y1: 594.8479614257812,
  x2: 524.4090576171875,
  y2: 627.77197265625,
  pageNumber: 57,
});
const evidenceRects = [
  pdfRect({
    x1: 109.03900146484375,
    y1: 594.8479614257812,
    x2: 524.4090576171875,
    y2: 607.77197265625,
    pageNumber: 57,
  }),
  pdfRect({
    x1: 85.0390625,
    y1: 614.8479614257812,
    x2: 508.8430480957031,
    y2: 627.77197265625,
    pageNumber: 57,
  }),
];

const rule = {
  rule_id: 'claim_evidence_inconsistency_check',
  title: '论点与论据一致性',
  description: '检查论文中的数值论点与候选实验论据是否矛盾。',
  default_severity: 'warning',
  default_enabled: true,
  execution_mode: 'semantic',
  uses_external_model: true,
  available: true,
};

const finding = {
  finding_id: 'f_claim_evidence_inconsistency_check_1',
  rule_id: rule.rule_id,
  message:
    '研究内容段落明确声称 Z-Solver 在 Yandex 测试集上的准确率为 80.0%；但实验结果段落报告 Z-Solver 在同一测试集上取得的是 60.5%，并在 Microsoft 和 Wikipedia 数据集上分别达到 79.8% 和 85.4%。该论点与正文后续实验数据中的同一指标不一致。',
  suggestion:
    '将研究内容中的 Yandex 准确率修正为与实验结果一致的 60.5%，或补充能够支持 80.0% 的新实验表格和设置说明；同时检查摘要、正文概述和实验表中的同一指标是否保持一致。',
  location: {
    type: 'pdf_bbox',
    page_number: 22,
    bounding_rect: claimRect,
    rects: [claimRect],
    text_excerpt: '在本研究的量化评测中, 本文测得Z-Solver 在Yandex 测试集上的准确率为80.0%。',
  },
  anchors: [
    {
      anchor_id: 'f_claim_evidence_inconsistency_check_1_claim',
      role: 'claim',
      label: '论点（第 22 页）',
      description: '研究内容中对 Yandex 准确率的陈述。',
      location: {
        type: 'pdf_bbox',
        page_number: 22,
        bounding_rect: claimRect,
        rects: [claimRect],
        text_excerpt: '在本研究的量化评测中, 本文测得Z-Solver 在Yandex 测试集上的准确率为80.0%。',
      },
    },
    {
      anchor_id: 'f_claim_evidence_inconsistency_check_1_evidence_1',
      role: 'evidence',
      label: '论据（第 57 页）',
      description: '实验结果段落报告的 Yandex 实测准确率。',
      location: {
        type: 'pdf_bbox',
        page_number: 57,
        bounding_rect: evidenceBoundingRect,
        rects: evidenceRects,
        text_excerpt:
          '相比之下,Z-Solver 在Yandex 测试集上取得了60.5% 的准确率, 并在Microsoft 和 Wikipedia 数据集上分别达到了79.8% 和85.4%。',
      },
    },
  ],
};

const builtInCase = {
  id: CLAIM_EVIDENCE_CASE_ID,
  title: '跨页数值论点与实验论据不一致',
  description: '研究内容声称 Yandex 准确率为 80.0%，实验结果报告为 60.5%。',
  pdf_filename: PDF_FILENAME,
  claim_page: 22,
  evidence_page: 57,
  rule,
  result: {
    type: 'paper_lint',
    paper_title: '零标注样本的文本验证码识别方法研究',
    ruleset: {
      id: 'built-in-review-case',
      name: '内置审查案例',
      version_number: 1,
      version_label: '案例 1',
    },
    rule_runs: [
      {
        rule_run_id: 'run_claim_evidence_inconsistency_check',
        rule_id: rule.rule_id,
        severity: 'warning',
        params: null,
        execution_status: 'completed',
        evidence_mode: 'derived',
        outcome: 'issues_found',
        message: null,
        findings: [finding],
      },
    ],
    summary: {
      rule_count: 1,
      completed_rule_count: 1,
      unsupported_rule_count: 0,
      error_rule_count: 0,
      issue_rule_count: 1,
      finding_count: 1,
      error_finding_count: 0,
      warning_finding_count: 1,
      info_finding_count: 0,
      derived_rule_count: 1,
    },
  },
};

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function listPaperLintExamples() {
  const { result, ...summary } = builtInCase;
  return { cases: [{ ...summary, finding_count: result.summary.finding_count }] };
}

function getPaperLintExample(caseId) {
  if (caseId !== CLAIM_EVIDENCE_CASE_ID) {
    throw createHttpError(404, '内置审查案例不存在');
  }
  return builtInCase;
}

async function readPaperLintExamplePdf(caseId) {
  getPaperLintExample(caseId);
  const pdfPath = path.join(resolveEngineBackendDir(), PDF_RELATIVE_PATH);
  let content;
  try {
    content = await fs.promises.readFile(pdfPath);
  } catch (error) {
    if (error?.code === 'ENOENT') throw createHttpError(503, '内置案例 PDF 尚未安装');
    throw error;
  }
  if (content.subarray(0, 5).toString('ascii') !== '%PDF-') {
    throw createHttpError(503, '内置案例 PDF 无法读取');
  }
  return { content, filename: PDF_FILENAME };
}

module.exports = {
  CLAIM_EVIDENCE_CASE_ID,
  getPaperLintExample,
  listPaperLintExamples,
  readPaperLintExamplePdf,
};
