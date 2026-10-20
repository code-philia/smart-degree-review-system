import apiClient from './index';

export type RepairSuggestionStatus = 'suggested' | 'insufficient_context' | 'evidence_conflict';

export type RepairSuggestion = {
  schema_version: 'repair-response-v2';
  rule_id: string;
  finding_id: string;
  status: RepairSuggestionStatus;
  actions: { instruction: string; evidence_ids: string[] }[];
  provenance: {
    provider: 'huawei_maas';
    model: string;
    model_version: string;
    prompt_version: string;
    context_sha256: string;
    generated_at: string;
  };
  usage: { input_tokens: number; output_tokens: number; attempts: number };
};

export type ArchiveFindingReference = {
  job_id: string;
  document_id: string;
  rule_id: string;
  finding_id: string;
};

export type PaperLintFindingReference = {
  report_id: string;
  rule_id: string;
  finding_id: string;
};

export const PAPER_LINT_REPAIR_RULE_IDS = new Set([
  'sjtu_rule_11', 'sjtu_rule_13', 'sjtu_rule_14', 'sjtu_rule_15', 'sjtu_rule_16',
  'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_29',
]);

const base = '/normative/repair-suggestions/archive-findings';

export async function evaluateArchiveFindingRepairSuggestion(reference: ArchiveFindingReference): Promise<{
  response: RepairSuggestion;
  cached: boolean;
}> {
  return (await apiClient.post(`${base}/evaluate`, reference, { timeout: 40_000 })).data;
}

export async function fetchArchiveFindingRepairSuggestions(
  reference: ArchiveFindingReference,
): Promise<RepairSuggestion[]> {
  const response = await apiClient.get<{ suggestions: Array<{ response: RepairSuggestion }> }>(base, {
    params: reference,
  });
  return response.data.suggestions.map((item) => item.response);
}

function paperLintReportSuggestionUrl(reportId: string) {
  return `/normative/paper-lint/reports/${encodeURIComponent(reportId)}/repair-suggestions`;
}

export async function fetchPaperLintFindingRepairSuggestion(
  reference: PaperLintFindingReference,
): Promise<RepairSuggestion | null> {
  const response = await apiClient.get<{ response: RepairSuggestion | null }>(
    paperLintReportSuggestionUrl(reference.report_id),
    { params: { rule_id: reference.rule_id, finding_id: reference.finding_id }, timeout: 40_000 },
  );
  return response.data.response;
}

export async function evaluatePaperLintFindingRepairSuggestion(
  reference: PaperLintFindingReference,
  { force = false }: { force?: boolean } = {},
): Promise<{ response: RepairSuggestion; cached: boolean }> {
  return (await apiClient.post(
    paperLintReportSuggestionUrl(reference.report_id),
    { rule_id: reference.rule_id, finding_id: reference.finding_id, force },
    { timeout: 40_000 },
  )).data;
}
