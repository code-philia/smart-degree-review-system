import apiClient from './index';

export type NormativeRuleCategory =
  | '章节顺序'
  | '标点配对'
  | '重复标点'
  | '日期格式'
  | '参考文献'
  | '文本质量';

export type NormativeSeverity = 'low' | 'medium' | 'high';

export type NormativeIssue = {
  rule_id: string;
  category: NormativeRuleCategory | string;
  severity: NormativeSeverity | string;
  line: number;
  column: number;
  excerpt: string;
  message: string;
  suggestion: string;
};

export type AnalyzeNormativeTextRequest = {
  text: string;
};

export type AnalyzeNormativeTextResponse = {
  issues: NormativeIssue[];
};

export async function analyzeDefaultNormativeText(
  payload: AnalyzeNormativeTextRequest,
): Promise<AnalyzeNormativeTextResponse> {
  const response = await apiClient.post<AnalyzeNormativeTextResponse>('/normative/analyze', payload);
  return response.data;
}
