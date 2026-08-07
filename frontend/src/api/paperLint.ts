import apiClient from './index';

export type PaperLintSeverity = 'error' | 'warning' | 'info';
export type PaperLintExecutionStatus = 'completed' | 'unsupported' | 'error';
export type PaperLintOutcome = 'passed' | 'issues_found' | 'inconclusive' | 'not_applicable';

export type PaperLintRule = {
  rule_id: string;
  title: string;
  description: string;
  default_severity: PaperLintSeverity;
  default_enabled: boolean;
  execution_mode: 'deterministic' | 'semantic';
  uses_external_model: boolean;
  available: boolean;
};

export type PaperLintCatalogResponse = {
  engine: 'review-pilot';
  mode: 'pdf_lint';
  semantic_model: 'deepseek-v4-flash';
  rules: PaperLintRule[];
};

export type PdfRect = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  width: number;
  height: number;
  page_number: number;
};

export type PdfBBoxLocation = {
  type: 'pdf_bbox';
  page_number: number;
  bounding_rect: PdfRect;
  rects: PdfRect[];
  text_excerpt?: string | null;
};

export type PdfPageLocation = {
  type: 'pdf_page';
  page_number: number;
  text_excerpt?: string | null;
};

export type PaperLintLocation = PdfBBoxLocation | PdfPageLocation;

export type PaperLintFindingAnchor = {
  anchor_id: string;
  role: string;
  label?: string | null;
  description?: string | null;
  location: PaperLintLocation;
};

export type PaperLintFinding = {
  finding_id: string;
  rule_id: string;
  message: string;
  suggestion?: string | null;
  location?: PaperLintLocation | null;
  anchors?: PaperLintFindingAnchor[];
};

export type PaperLintRuleRun = {
  rule_run_id: string;
  rule_id: string;
  severity: PaperLintSeverity;
  params?: Record<string, unknown> | null;
  execution_status: PaperLintExecutionStatus;
  evidence_mode?: 'native' | 'derived' | 'unsupported' | null;
  outcome: PaperLintOutcome;
  message?: string | null;
  findings: PaperLintFinding[];
};

export type PaperLintSummary = {
  rule_count: number;
  completed_rule_count: number;
  unsupported_rule_count: number;
  error_rule_count: number;
  issue_rule_count: number;
  finding_count: number;
  error_finding_count: number;
  warning_finding_count: number;
  info_finding_count: number;
  derived_rule_count: number;
};

export type PaperLintResult = {
  type: 'paper_lint';
  paper_title: string;
  ruleset: {
    id: string;
    name: string;
    version_number: number;
    version_label: string;
  };
  rule_runs: PaperLintRuleRun[];
  summary: PaperLintSummary;
};

export type PaperLintRunResponse = {
  source_filename: string;
  selected_rule_ids: string[];
  processed_at: string;
  result: PaperLintResult;
};

export async function fetchReviewPilotPaperLintRules(): Promise<PaperLintCatalogResponse> {
  const response = await apiClient.get<PaperLintCatalogResponse>('/normative/paper-lint/rules', {
    timeout: 60_000,
  });
  return response.data;
}

export async function runReviewPilotPaperLint(
  file: File,
  selectedRuleIds: string[],
  externalProcessingConsent = false,
): Promise<PaperLintRunResponse> {
  const response = await apiClient.post<PaperLintRunResponse>('/normative/paper-lint/run', file, {
    params: { filename: file.name },
    headers: {
      'Content-Type': 'application/pdf',
      'X-Paper-Lint-Rule-Ids': selectedRuleIds.join(','),
      ...(externalProcessingConsent ? { 'X-Paper-Lint-External-Processing-Consent': 'confirmed' } : {}),
    },
    timeout: 310_000,
  });
  return response.data;
}
