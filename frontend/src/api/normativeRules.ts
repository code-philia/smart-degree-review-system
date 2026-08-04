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

export type DuplicationDetectionRequest = {
  text: string;
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  threshold?: number;
};

export type DuplicationSimilaritySegment = {
  source_start: number;
  source_end: number;
  sample_start: number;
  sample_end: number;
  source_excerpt: string;
  sample_excerpt: string;
};

export type DuplicationSimilarityMatch = {
  sample_id: string;
  title: string;
  subject: string;
  year: number;
  jaccard_score: number;
  matched_character_count: number;
  segments: DuplicationSimilaritySegment[];
};

export type DuplicationRiskFactorKey =
  | 'paragraph_duplication_rate'
  | 'sentence_length_low_variation'
  | 'template_connector_density'
  | 'vague_phrase_density';

export type DuplicationRiskReport = {
  score: number;
  label: 'heuristic_only';
  explanation: string;
  factors: Record<DuplicationRiskFactorKey, number>;
  weights: Record<DuplicationRiskFactorKey, number>;
};

export type DuplicationDetectionResponse = {
  status: 'completed' | 'no_samples';
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  threshold: number;
  effective_character_count: number;
  total_similarity_rate: number;
  sample_count: number;
  top_matches: DuplicationSimilarityMatch[];
  risk: DuplicationRiskReport;
};

export type DuplicationHistoryRecord = {
  id: string;
  user_id: string;
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  original_text: string;
  total_similarity_rate: number;
  writing_risk_score: number;
  sample_count: number;
  report_json: DuplicationDetectionResponse | Record<string, unknown>;
  created_at: string;
};

export type WholePolishLevel = 'basic' | 'standard' | 'enhanced';
export type LocalPolishLevel = WholePolishLevel;

export type WholePolishChange = {
  original_text: string;
  new_text: string;
  position: number;
  rule: string;
  reason?: string;
};

export type LocalPolishDiffSegment = {
  type: 'unchanged' | 'added' | 'deleted' | 'replacement' | 'replaced' | 'format';
  text: string;
  original_text?: string;
  new_text?: string;
  position: number;
  rule?: string;
};

export type WholePolishRequest = {
  text: string;
  level: WholePolishLevel;
  source_type: 'paste' | 'file';
  source_filename?: string | null;
};

export type LocalPolishRequest = {
  text: string;
  level: LocalPolishLevel;
  retry_of?: string | null;
};

export type WholePolishResult = {
  id: string;
  user_id: string;
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  original_text: string;
  polished_text: string;
  level: WholePolishLevel;
  changes: WholePolishChange[];
  created_at: string;
};

export type LocalPolishResult = {
  id: string;
  user_id: string;
  original_text: string;
  polished_text: string;
  level: LocalPolishLevel;
  rule_version: string;
  changes: WholePolishChange[];
  diff_segments: LocalPolishDiffSegment[];
  source_result_id?: string | null;
  retry_of?: string | null;
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

export async function createDuplicationDetection(
  payload: DuplicationDetectionRequest,
): Promise<DuplicationDetectionResponse> {
  const response = await apiClient.post<DuplicationDetectionResponse>('/normative/duplication-detections', payload);
  return response.data;
}

export async function fetchDuplicationDetectionHistory(): Promise<DuplicationHistoryRecord[]> {
  const response = await apiClient.get<{ records: DuplicationHistoryRecord[] }>('/normative/duplication-detection-reports');
  return response.data.records;
}

export async function fetchDuplicationDetectionReport(reportId: string): Promise<DuplicationHistoryRecord> {
  const response = await apiClient.get<DuplicationHistoryRecord>(`/normative/duplication-detection-reports/${reportId}`);
  return response.data;
}

export async function downloadDuplicationReportJson(reportId: string): Promise<Blob> {
  const response = await apiClient.get(`/normative/duplication-detection-reports/${reportId}/download`, {
    responseType: 'blob',
    headers: { Accept: 'application/json' },
  });
  return response.data;
}

export async function createWholePolishResult(payload: WholePolishRequest): Promise<WholePolishResult> {
  const response = await apiClient.post<WholePolishResult>('/normative/whole-polish-results', payload);
  return response.data;
}

export async function createLocalPolishResult(payload: LocalPolishRequest): Promise<LocalPolishResult> {
  const response = await apiClient.post<LocalPolishResult>('/normative/local-polish-results', payload);
  return response.data;
}

export async function fetchLocalPolishResult(resultId: string): Promise<LocalPolishResult> {
  const response = await apiClient.get<LocalPolishResult>(`/normative/local-polish-results/${resultId}`);
  return response.data;
}

export async function fetchWholePolishResult(resultId: string): Promise<WholePolishResult> {
  const response = await apiClient.get<WholePolishResult>(`/normative/whole-polish-results/${resultId}`);
  return response.data;
}

export async function downloadWholePolishText(resultId: string): Promise<Blob> {
  const response = await apiClient.get(`/normative/whole-polish-results/${resultId}/download`, {
    responseType: 'blob',
    headers: { Accept: 'text/plain' },
  });
  return response.data;
}

export async function fetchNormativeDetectionHistory(): Promise<DetectionTaskResponse[]> {
  const response = await apiClient.get<{ records: DetectionTaskResponse[] }>('/normative/detection-reports');
  return response.data.records;
}

export async function fetchNormativeDetectionReport(taskId: string): Promise<DetectionTaskResponse> {
  const response = await apiClient.get<DetectionTaskResponse>(`/normative/detection-reports/${taskId}`);
  return response.data;
}

export async function downloadNormativeReportJson(taskId: string): Promise<Blob> {
  const response = await apiClient.get(`/normative/detection-reports/${taskId}/download`, {
    responseType: 'blob',
    headers: { Accept: 'application/json' },
  });
  return response.data;
}
