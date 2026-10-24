import apiClient from './index';
import basicRepairRules from '../../../shared/basic-repair-rules.json';

export type RepairSuggestionStatus = 'suggested' | 'insufficient_context' | 'evidence_conflict';

export type RepairSuggestion = {
  suggestion_id?: string;
  generation?: number;
  schema_version: 'repair-response-v2';
  rule_id: string;
  finding_id: string;
  status: RepairSuggestionStatus;
  rationale?: string;
  missing_context?: string[];
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

// Kept for the hidden archive workflow. It is intentionally not used by MVP
// paper reports, whose visible repair actions are restricted to four rules.
export const ARCHIVE_REPAIR_RULE_IDS = new Set([
  ...basicRepairRules.map(rule => rule.rule_id),
  'sjtu_rule_11', 'sjtu_rule_13', 'sjtu_rule_14', 'sjtu_rule_15', 'sjtu_rule_16',
  'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_29',
  'sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33',
]);

const base = '/normative/repair-suggestions/archive-findings';

export async function evaluateArchiveFindingRepairSuggestion(reference: ArchiveFindingReference, {force = false}: {force?: boolean} = {}): Promise<{
  response: RepairSuggestion;
  cached: boolean;
}> {
  return (await apiClient.post(`${base}/evaluate`, force ? {...reference, force: true} : reference, { timeout: 40_000 })).data;
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
  const response = await apiClient.get<{ response: RepairSuggestion | null; suggestion_id?: string; generation?: number }>(
    paperLintReportSuggestionUrl(reference.report_id),
    { params: { rule_id: reference.rule_id, finding_id: reference.finding_id }, timeout: 40_000 },
  );
  return response.data.response ? { ...response.data.response, suggestion_id: response.data.suggestion_id || undefined, generation: response.data.generation || undefined } : null;
}

export async function evaluatePaperLintFindingRepairSuggestion(
  reference: PaperLintFindingReference,
  { force = false }: { force?: boolean } = {},
): Promise<{ response: RepairSuggestion; cached: boolean }> {
  const result = (await apiClient.post<{
    response: RepairSuggestion;
    suggestion_id?: string | null;
    generation?: number | null;
    cached: boolean;
  }>(
    paperLintReportSuggestionUrl(reference.report_id),
    { rule_id: reference.rule_id, finding_id: reference.finding_id, force },
    { timeout: 40_000 },
  )).data;
  return {
    ...result,
    response: {
      ...result.response,
      suggestion_id: result.suggestion_id || undefined,
      generation: result.generation || undefined,
    },
  };
}
