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

export type DetectionTaskStatus = 'pending' | 'running' | 'completed';

export type CreateDetectionTaskRequest = {
  text: string;
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  selected_rule_ids?: string[];
};

export type DetectionTaskResponse = {
  id: string;
  user_id: string;
  status: DetectionTaskStatus;
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  original_text: string;
  rule_snapshot: Array<Record<string, unknown>>;
  issues: NormativeIssue[];
  severity_counts: Record<string, number>;
  created_at: string;
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

export async function createNormativeDetectionTask(
  payload: CreateDetectionTaskRequest,
): Promise<DetectionTaskResponse> {
  const response = await apiClient.post<DetectionTaskResponse>('/normative/detection-tasks', payload);
  return response.data;
}
