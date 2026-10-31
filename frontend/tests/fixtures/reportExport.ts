import type { PaperLintRunResponse } from '../../src/api/paperLint';
const summary = {
  rule_count: 1,
  unsupported_rule_count: 0,
  error_rule_count: 0,
  issue_rule_count: 1,
  finding_count: 1,
  error_finding_count: 0,
  warning_finding_count: 1,
  info_finding_count: 0,
  derived_rule_count: 0,
};
export const fixture: PaperLintRunResponse = {
  id: 'export-report',
  source_filename: '中文论文<>.pdf',
  selected_rule_ids: ['sjtu_rule_15'],
  created_at: '2026-10-31T01:02:03Z',
  summary: { ...summary, ruleset_label: 'v1' },
  result: {
    type: 'paper_lint',
    paper_title: '学位论文',
    ruleset: { id: 'rules', name: '论文规范', version_number: 1, version_label: 'v1' },
    summary,
    rule_runs: [
      {
        rule_id: 'sjtu_rule_15',
        rule_run_id: 'run',
        severity: 'warning',
        execution_status: 'completed',
        outcome: 'issues_found',
        findings: [
          {
            finding_id: 'f1',
            rule_id: 'sjtu_rule_15',
            message: '问题中文 <script> *内容*\n第二行',
            suggestion: '已有本地建议',
            location: { type: 'pdf_page', page_number: 3, text_excerpt: '原文证据' },
            anchors: [
              {
                anchor_id: 'a',
                role: 'evidence',
                label: '另一个位置',
                location: { type: 'pdf_page', page_number: 5, text_excerpt: '第二处证据' },
              },
            ],
            evidence: [{ id: 'e', quote: '引用证据', url: 'https://example.com/paper' }],
            basis_details: [{ id: 'b', text: '检查依据' }],
          },
        ],
      },
    ],
  },
};
