import apiClient from './index';
export type ExampleAnnotation = {
  type: 'focus' | 'pass' | 'fail' | 'exception' | 'note';
  block_type?: 'text' | 'figure' | 'table' | 'equation';
  page_number: number;
  text_excerpt: string;
  note?: string;
  bounding_rect?: unknown;
};
export type ExampleDocument = {
  id: string;
  source_filename: string;
  annotations: ExampleAnnotation[];
  created_at: string;
  updated_at: string;
};
export type RuleDefinition = {
  title: string;
  check_description: string;
  criteria: string[];
  exception_notes: string[];
  suggestion_template: string;
};
export type ExampleRule = {
  id: string;
  name: string;
  intent: string;
  status: 'enabled' | 'disabled';
  version: number;
  definition: RuleDefinition;
  created_at: string;
  updated_at: string;
};
export type RuleResult = {
  rule_id: string;
  outcome: 'pass' | 'issue' | 'not_applicable' | 'undetermined';
  conclusion: string;
  suggestion: string;
  evidence: { page_number: number; text_excerpt: string; bounding_rect?: unknown }[];
};
export type ExampleReport = {
  id: string;
  source_filename: string;
  rule_snapshots: { rule_id: string; name: string; version: number; definition: RuleDefinition }[];
  result?: {
    disclaimer: string;
    rule_results: RuleResult[];
    summary: { rule_count: number; issue_count: number; pass_count: number; undetermined_count: number };
  };
  summary?: Record<string, number>;
  created_at: string;
};
export const listExampleDocuments = async () =>
  (await apiClient.get('/example-rule-check/documents')).data.records as ExampleDocument[];
export async function uploadExampleDocument(file: File) {
  return (
    await apiClient.post(`/example-rule-check/documents?filename=${encodeURIComponent(file.name)}`, file, {
      headers: { 'Content-Type': 'application/pdf' },
      timeout: 70_000,
    })
  ).data as ExampleDocument;
}
export const updateExampleAnnotations = async (id: string, annotations: ExampleAnnotation[]) =>
  (await apiClient.put(`/example-rule-check/documents/${id}/annotations`, { annotations })).data as ExampleDocument;
export const exampleDocumentPdf = async (id: string) =>
  (await apiClient.get(`/example-rule-check/documents/${id}/pdf`, { responseType: 'blob' })).data as Blob;
export const generateExampleRule = async (intent: string, document_ids: string[]) =>
  (
    await apiClient.post(
      '/example-rule-check/generate',
      { intent, document_ids, external_processing_consent: true },
      { timeout: 60_000 },
    )
  ).data.definition as RuleDefinition;
export const trialExampleRule = async (body: {
  name: string;
  intent: string;
  definition: RuleDefinition;
  document_ids: string[];
}) =>
  (
    await apiClient.post(
      '/example-rule-check/trial',
      { ...body, external_processing_consent: true },
      { timeout: 60_000 },
    )
  ).data as { rule_results: RuleResult[] };
export const listExampleRules = async () =>
  (await apiClient.get('/example-rule-check/rules')).data.records as ExampleRule[];
export const createExampleRule = async (body: {
  name: string;
  intent: string;
  status: 'enabled' | 'disabled';
  definition: RuleDefinition;
}) => (await apiClient.post('/example-rule-check/rules', body)).data as ExampleRule;
export const updateExampleRule = async (
  id: string,
  body: { name: string; intent: string; status: 'enabled' | 'disabled'; definition: RuleDefinition },
) => (await apiClient.put(`/example-rule-check/rules/${id}`, body)).data as ExampleRule;
export const deleteExampleRule = async (id: string) => apiClient.delete(`/example-rule-check/rules/${id}`);
export const listExampleReports = async () =>
  (await apiClient.get('/example-rule-check/reports')).data.records as ExampleReport[];
export const getExampleReport = async (id: string) =>
  (await apiClient.get(`/example-rule-check/reports/${id}`)).data as ExampleReport;
export const exampleReportPdf = async (id: string) =>
  (await apiClient.get(`/example-rule-check/reports/${id}/pdf`, { responseType: 'blob' })).data as Blob;
export async function runExampleReport(file: File, rule_ids: string[]) {
  if (!window.confirm('我确认待检论文中被选中的相关文本允许发送至 DeepSeek。是否继续检测？'))
    throw new Error('未确认外发，未发起检测');
  const request = btoa(JSON.stringify({ rule_ids, external_processing_consent: true }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return (
    await apiClient.post(`/example-rule-check/reports?filename=${encodeURIComponent(file.name)}`, file, {
      headers: { 'Content-Type': 'application/pdf', 'X-Example-Rule-Request': request },
      timeout: 70_000,
    })
  ).data as ExampleReport;
}
