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

export type ReviewRubricTemplate = {
  template_id: string;
  name: string;
  required_sections: string[];
  minimum_reference_count: number;
};

export type ReviewRubricScoreItem = {
  key: string;
  label: string;
  points: number;
};

export type ReviewRubricPassingRule = {
  minimum_objective_score: number;
  no_required_section_missing: boolean;
  pass_label: string;
  revise_label: string;
};

export type ReviewRubricsResponse = {
  templates: ReviewRubricTemplate[];
  shared_score_items: ReviewRubricScoreItem[];
  passing_rule: ReviewRubricPassingRule;
};

export type AiReviewSourceType = 'paste' | 'file';

export type AiReviewRunRequest = {
  thesis_title: string;
  template_id: string;
  text: string;
  source_type: AiReviewSourceType;
  source_filename?: string | null;
};

export type AiReviewSectionSnapshot = {
  name: string;
  present: boolean;
};

export type AiReviewScoreItem = ReviewRubricScoreItem & {
  score: number;
  findings: string[];
};

export type AiReviewRunResponse = {
  id: string;
  user_id: string;
  thesis_title: string;
  template_id: string;
  source_type: AiReviewSourceType;
  source_filename?: string | null;
  original_text: string;
  section_snapshot: AiReviewSectionSnapshot[];
  reference_count: number;
  character_count: number;
  normative_issues: NormativeIssue[];
  score_items: AiReviewScoreItem[];
  total_score: number;
  result_label: string;
  missing_sections: string[];
  rubric_snapshot: ReviewRubricsResponse | Record<string, unknown>;
  created_at: string;
};

export type AiReviewSubjectiveConfirmationItem = {
  key: string;
  label: string;
  status: '待人工确认';
};

export type AiReviewResultResponse = AiReviewRunResponse & {
  objective_score_total: number;
  subjective_confirmation_items: AiReviewSubjectiveConfirmationItem[];
};

export type AiReviewHistoryRecord = Pick<
  AiReviewRunResponse,
  'id' | 'user_id' | 'thesis_title' | 'template_id' | 'total_score' | 'result_label' | 'created_at'
>;

export type DetectionLedgerType = 'normative' | 'aigc' | 'duplication' | 'polish' | 'innovation' | 'ai_review';

export type LedgerRecordFilters = {
  student?: string;
  detection_type?: DetectionLedgerType | '';
  from?: string;
  to?: string;
  latest_only?: boolean;
};

export type DetectionLedgerRecord = {
  id: string;
  source_record_id: string;
  college_id: string | null;
  college_name: string;
  student_id: string;
  student_number: string;
  student_name: string;
  supervisor_id: string | null;
  supervisor_name: string;
  student_category: string;
  thesis_title: string;
  detection_type: DetectionLedgerType;
  detection_type_label: string;
  template_name: string;
  core_result: string;
  detail_url: string;
  is_latest: boolean;
  created_at: string;
};

export type DetectionLedgerTypeStat = {
  detection_type: DetectionLedgerType;
  detection_type_label: string;
  record_count: number;
  student_count: number;
  total_records?: number;
  total_students?: number;
  today_count: number;
};

export type DetectionLedgerTrendPoint = {
  date: string;
  count: number;
  record_count?: number;
  student_count?: number;
  total_records?: number;
  total_students?: number;
};

export type DetectionLedgerFilteredStats = {
  filters: LedgerRecordFilters;
  total_records: number;
  total_students: number;
  today_count: number;
  by_type: DetectionLedgerTypeStat[];
  daily_trend: DetectionLedgerTrendPoint[];
  generated_at: string;
};

export type QualityMetricKey = 'normative' | 'originality' | 'innovation' | 'review_base';

export type QualityMetricSummary = {
  key: QualityMetricKey;
  label: string;
  average_score: number | null;
  sample_count: number;
  missing_count: number;
  distribution: Array<{ range: string; count: number }>;
};

export type QualityDashboardStudentMetric = {
  student_id: string;
  student_name: string;
  scores: Record<QualityMetricKey, number | null>;
};

export type QualityDashboardResponse = {
  filters: LedgerRecordFilters;
  sample_count: number;
  metrics: QualityMetricSummary[];
  students: QualityDashboardStudentMetric[];
  generated_at: string;
};

export type StudentQualityPortraitMetric = {
  key: QualityMetricKey;
  label: string;
  score: number | null;
  source_record_id: string | null;
  source_type: DetectionLedgerType;
  source_label: string;
  source_created_at: string | null;
  detail_url: string | null;
};

export type StudentQualityPortraitResponse = {
  student: {
    student_id: string;
    student_number: string;
    student_name: string;
    college_id: string | null;
    college_name: string;
    supervisor_id: string | null;
    supervisor_name: string;
    student_category: string;
    thesis_title: string | null;
  };
  metrics: StudentQualityPortraitMetric[];
  overall_score: number | null;
  completeness: {
    complete: boolean;
    missing_metric_keys: QualityMetricKey[];
    missing_metric_labels: string[];
  };
  generated_at: string;
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

export type InnovationDegreeType = 'doctoral' | 'master';

export type InnovationScoreDimensionKey =
  | 'research_topic'
  | 'research_method'
  | 'research_content'
  | 'research_conclusion'
  | 'application_value';

export type InnovationScoreRequest = {
  degree_type: InnovationDegreeType;
  levels: Record<InnovationScoreDimensionKey, number>;
};

export type InnovationAssessmentDimensionInput = {
  level: number;
  evidence: string;
  improvement_plan: string;
};

export type InnovationAssessmentRequest = {
  thesis_title: string;
  degree_type: InnovationDegreeType;
  primary_discipline: string;
  secondary_discipline: string;
  research_direction: string;
  dimensions: Record<InnovationScoreDimensionKey, InnovationAssessmentDimensionInput>;
};

export type InnovationScoreDimensionReport = {
  key: InnovationScoreDimensionKey;
  label: string;
  level: number;
  raw_score: number;
  weight: number;
  weighted_score: number;
};

export type InnovationScoreResponse = {
  degree_type: InnovationDegreeType;
  total_score: number;
  grade_label: '优秀' | '良好' | '一般' | '待提升';
  formula: string;
  dimensions: InnovationScoreDimensionReport[];
  input: InnovationScoreRequest;
};

export type InnovationAssessmentResponse = InnovationScoreResponse & {
  id: string;
  user_id: string;
  thesis_title: string;
  primary_discipline: string;
  secondary_discipline: string;
  research_direction: string;
  input_snapshot: InnovationAssessmentRequest;
  scoring_snapshot: InnovationScoreResponse;
  disclaimer: string;
  created_at: string;
};

export type InnovationHistoryRecord = {
  id: string;
  user_id: string;
  thesis_title: string;
  degree_type: InnovationDegreeType;
  total_score: number;
  grade_label: InnovationScoreResponse['grade_label'];
  created_at: string;
};

export type PolishHistoryRecord = {
  id: string;
  user_id: string;
  polish_type: 'whole' | 'local';
  source_type: 'paste' | 'file';
  source_filename?: string | null;
  document_name: string;
  original_text: string;
  polished_text: string;
  level: WholePolishLevel;
  changes: WholePolishChange[];
  diff_segments: LocalPolishDiffSegment[];
  change_count: number;
  rule_version?: string;
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

export async function fetchReviewRubrics(): Promise<ReviewRubricsResponse> {
  const response = await apiClient.get<ReviewRubricsResponse>('/normative/review-rubrics');
  return response.data;
}

export async function createAiReviewRun(payload: AiReviewRunRequest): Promise<AiReviewRunResponse> {
  const response = await apiClient.post<AiReviewRunResponse>('/normative/ai-review-runs', payload);
  return response.data;
}

export async function fetchAiReviewResult(reviewRunId: string): Promise<AiReviewResultResponse> {
  const response = await apiClient.get<AiReviewResultResponse>(`/normative/ai-review-runs/${reviewRunId}`);
  return response.data;
}

export async function downloadAiReviewResultJson(reviewRunId: string): Promise<Blob> {
  const response = await apiClient.get(`/normative/ai-review-runs/${reviewRunId}/download`, {
    responseType: 'blob',
    headers: { Accept: 'application/json' },
  });
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

export async function calculateInnovationScore(payload: InnovationScoreRequest): Promise<InnovationScoreResponse> {
  const response = await apiClient.post<InnovationScoreResponse>('/normative/innovation-scores', payload);
  return response.data;
}

export async function createInnovationAssessment(
  payload: InnovationAssessmentRequest,
): Promise<InnovationAssessmentResponse> {
  const response = await apiClient.post<InnovationAssessmentResponse>('/normative/innovation-assessments', payload);
  return response.data;
}

export async function fetchInnovationHistory(): Promise<InnovationHistoryRecord[]> {
  const response = await apiClient.get<{ records: InnovationHistoryRecord[] }>('/normative/innovation-assessments');
  return response.data.records;
}

export async function fetchInnovationReport(reportId: string): Promise<InnovationAssessmentResponse> {
  const response = await apiClient.get<InnovationAssessmentResponse>(`/normative/innovation-assessments/${reportId}`);
  return response.data;
}

export async function downloadInnovationReportJson(reportId: string): Promise<Blob> {
  const response = await apiClient.get(`/normative/innovation-assessments/${reportId}/download`, {
    responseType: 'blob',
    headers: { Accept: 'application/json' },
  });
  return response.data;
}

export async function fetchPolishHistory(): Promise<PolishHistoryRecord[]> {
  const response = await apiClient.get<{ records: PolishHistoryRecord[] }>('/normative/polish-history');
  return response.data.records;
}

export async function fetchPolishHistoryRecord(polishType: PolishHistoryRecord['polish_type'], resultId: string): Promise<PolishHistoryRecord> {
  const response = await apiClient.get<PolishHistoryRecord>(`/normative/polish-history/${polishType}/${resultId}`);
  return response.data;
}

export async function downloadPolishResultText(polishType: PolishHistoryRecord['polish_type'], resultId: string): Promise<Blob> {
  const response = await apiClient.get(`/normative/polish-history/${polishType}/${resultId}/download`, {
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

function toLedgerRecordParams(filters: LedgerRecordFilters = {}): Record<string, string> {
  const params: Record<string, string> = {};
  if (filters.student) params.student = filters.student;
  if (filters.detection_type) params.detection_type = filters.detection_type;
  if (filters.from) params.from = filters.from;
  if (filters.to) params.to = filters.to;
  if (filters.latest_only !== undefined) params.latest_only = String(filters.latest_only);
  return params;
}

export async function fetchDetectionLedgerRecords(filters: LedgerRecordFilters = {}): Promise<DetectionLedgerRecord[]> {
  const response = await apiClient.get<{ records: DetectionLedgerRecord[] }>('/normative/ledger-records', {
    params: toLedgerRecordParams(filters),
  });
  return response.data.records;
}

export async function fetchDetectionLedgerRecord(recordId: string): Promise<DetectionLedgerRecord> {
  const response = await apiClient.get<DetectionLedgerRecord>(`/normative/ledger-records/${recordId}`);
  return response.data;
}

export async function fetchDetectionLedgerFilteredStats(
  filters: LedgerRecordFilters = {},
): Promise<DetectionLedgerFilteredStats> {
  const response = await apiClient.get<DetectionLedgerFilteredStats>('/normative/ledger-records/stats', {
    params: toLedgerRecordParams(filters),
  });
  return response.data;
}

export async function fetchQualityDashboard(filters: LedgerRecordFilters = {}): Promise<QualityDashboardResponse> {
  const response = await apiClient.get<QualityDashboardResponse>('/normative/ledger-records/quality-dashboard', {
    params: toLedgerRecordParams(filters),
  });
  return response.data;
}

export async function fetchStudentQualityPortrait(
  studentId: string,
  filters: Pick<LedgerRecordFilters, 'from' | 'to'> = {},
): Promise<StudentQualityPortraitResponse> {
  const response = await apiClient.get<StudentQualityPortraitResponse>(
    `/normative/ledger-records/student-quality-portrait/${studentId}`,
    { params: toLedgerRecordParams({ ...filters, latest_only: true }) },
  );
  return response.data;
}

export async function downloadDetectionLedgerCsv(filters: LedgerRecordFilters = {}): Promise<Blob> {
  const response = await apiClient.get('/normative/ledger-records/export.csv', {
    params: toLedgerRecordParams(filters),
    responseType: 'blob',
    headers: { Accept: 'text/csv' },
  });
  return response.data;
}

export async function fetchAiReviewHistory(): Promise<AiReviewHistoryRecord[]> {
  const response = await apiClient.get<{ records: AiReviewHistoryRecord[] }>('/normative/ai-review-runs');
  return response.data.records;
}
