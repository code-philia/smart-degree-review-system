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
