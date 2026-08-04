import apiClient from './index';
import type { NormativeRuleCategory, NormativeSeverity } from './normativeRules';

export type RuleScopeLevel = 'national' | 'school' | 'college';

export type RuleConfigScope = {
  level: RuleScopeLevel;
  college_id?: string | null;
};

export type RuleConfigDto = {
  rule_id: string;
  title: string;
  category: NormativeRuleCategory | string;
  severity: NormativeSeverity | string;
  enabled: boolean;
  match_params: Record<string, unknown>;
  prompt: string;
  source: RuleScopeLevel;
  college_id?: string | null;
};

export type RuleConfigListResponse = {
  scope: RuleConfigScope;
  rules: RuleConfigDto[];
};

export type PublishRuleConfigRequest = {
  scope: Exclude<RuleScopeLevel, 'national'>;
  college_id?: string | null;
  rule: Omit<RuleConfigDto, 'source' | 'college_id'>;
};

export type ResetCollegeRuleRequest = {
  college_id: string;
  rule_id: string;
};

export type ImportRuleDraftTemplateResponse = {
  scope: RuleConfigScope;
  imported_count: number;
  draft_batch_id: string;
  drafts: Array<Pick<RuleConfigDto, 'rule_id' | 'title' | 'category' | 'severity' | 'enabled'>>;
};

export type ImportRuleDraftTemplateError = {
  item_index?: number;
  field?: string;
  reason: string;
};

export async function fetchRuleConfigurations(scope?: Partial<RuleConfigScope>): Promise<RuleConfigListResponse> {
  const response = await apiClient.get<RuleConfigListResponse>('/normative/rule-configs', { params: scope });
  return response.data;
}

export async function publishRuleConfiguration(payload: PublishRuleConfigRequest): Promise<RuleConfigListResponse> {
  const response = await apiClient.put<RuleConfigListResponse>('/normative/rule-configs', payload);
  return response.data;
}

export async function resetCollegeRuleConfiguration(payload: ResetCollegeRuleRequest): Promise<RuleConfigListResponse> {
  const response = await apiClient.post<RuleConfigListResponse>('/normative/rule-configs/reset-college', payload);
  return response.data;
}

export async function importRuleDraftTemplate(file: File): Promise<ImportRuleDraftTemplateResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<ImportRuleDraftTemplateResponse>('/normative/rule-drafts/import', formData, {
    headers: { 'Content-Type': undefined },
  });
  return response.data;
}
