import apiClient from './index';
import type { PaperLintResult, PaperLintRule } from './paperLint';

export type ArchiveJob = {
  id: string;
  selected_rule_ids: string[];
  status: 'running' | 'completed' | 'failed';
  total_count: number;
  completed_count: number;
  failed_count: number;
  inconclusive_count: number;
  finding_count: number;
  created_at: string;
  finished_at: string | null;
};
export type ArchiveDocument = {
  id: string;
  job_id: string;
  relative_path: string;
  filename: string;
  size_bytes: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  finding_count: number;
  rule_outcomes: Record<string, string>;
  error_message: string | null;
  result?: PaperLintResult | null;
};
export type ArchiveCatalog = { rules: PaperLintRule[]; paper_count: number };
export type ArchiveDocumentPage = { items: ArchiveDocument[]; total: number; page: number; page_size: number };
const base = '/normative/archive-scans';
export async function fetchArchiveCatalog(): Promise<ArchiveCatalog> {
  return (await apiClient.get<ArchiveCatalog>(base)).data;
}
export async function fetchArchiveJobs(): Promise<{ jobs: ArchiveJob[] }> {
  return (await apiClient.get<{ jobs: ArchiveJob[] }>(`${base}/jobs`)).data;
}
export async function startArchiveJob(ruleIds: string[]): Promise<{ job: ArchiveJob }> {
  return (await apiClient.post<{ job: ArchiveJob }>(`${base}/jobs`, { selected_rule_ids: ruleIds }, { timeout: 30000 }))
    .data;
}
export async function deleteArchiveJob(id: string): Promise<void> {
  await apiClient.delete(`${base}/jobs/${encodeURIComponent(id)}`);
}
export async function fetchArchiveJob(id: string): Promise<{ job: ArchiveJob }> {
  return (await apiClient.get<{ job: ArchiveJob }>(`${base}/jobs/${id}`)).data;
}
export async function fetchArchiveDocuments(
  id: string,
  params: { rule_id?: string; outcome?: string; q?: string; page?: number } = {},
): Promise<ArchiveDocumentPage> {
  return (await apiClient.get<ArchiveDocumentPage>(`${base}/jobs/${id}/documents`, { params })).data;
}
export async function fetchArchiveDocument(jobId: string, documentId: string): Promise<{ document: ArchiveDocument }> {
  return (await apiClient.get<{ document: ArchiveDocument }>(`${base}/jobs/${jobId}/documents/${documentId}`)).data;
}
export function archivePdfUrl(jobId: string, documentId: string): string {
  return `/api${base}/jobs/${encodeURIComponent(jobId)}/documents/${encodeURIComponent(documentId)}/pdf`;
}
