import apiClient from './index';
import type { PaperLintReportSummary, PaperLintRule, PaperLintRunResponse } from './paperLint';

export type SupervisionOwner = { id: string; username: string; display_name: string | null };
export type SupervisionSummary = { users: number; reports: number; feedback: number; negative_feedback: number };
export type SupervisionReportType = 'paper_lint' | 'normative' | 'duplication' | 'example';
export type SupervisionReport = { id: string; report_type?: SupervisionReportType; type_label?: string; source_filename: string; created_at: string; owner: SupervisionOwner; summary: PaperLintReportSummary | null; unavailable?: boolean };
export type SupervisionReportDetail = { owner: SupervisionOwner } & (
  { report: PaperLintRunResponse; legacy?: never } |
  { report?: never; legacy: { id: string; report_type: SupervisionReportType; type_label: string; source_filename: string; created_at: string; original_text: string; saved_result: unknown; has_pdf: boolean } }
);
export type SupervisionFeedback = {
  id: string; type: 'system' | 'finding' | 'suggestion'; type_label: string;
  username: string; display_name: string | null; user_id: string;
  report_id: string | null; source_filename: string | null; rule_id: string | null; rule_title: string | null;
  finding_text: string | null; feedback_value: 'positive' | 'negative' | null; feedback_label: string;
  reason_label: string; reason_text: string | null; comment: string | null;
  satisfaction_score: number | null; improvement_labels: string[]; generation: number | null;
  created_at: string; updated_at: string;
  saved_suggestion: { id: string; generation: number; status: string; actions: { instruction: string; original_text?: string; replacement?: string }[] } | null;
};
export type SupervisionPage<T> = { items: T[]; total: number; page: number; page_size: number };
export const fetchSupervisionSummary = async (signal?: AbortSignal) =>
  (await apiClient.get<SupervisionSummary>('/supervision/summary', { signal })).data;
export const fetchSupervisionReports = async (params: { page: number; q: string; type?: string; search_field?: string }, signal?: AbortSignal) =>
  (await apiClient.get<SupervisionPage<SupervisionReport>>('/supervision/reports', { params, signal })).data;
export const fetchSupervisionFeedback = async (params: { page: number; q: string; type: string; value: string; search_field?: string }, signal?: AbortSignal) =>
  (await apiClient.get<SupervisionPage<SupervisionFeedback>>('/supervision/feedback', { params, signal })).data;
export const fetchSupervisionReport = async (id: string, signal?: AbortSignal, type = 'paper_lint') =>
  (await apiClient.get<SupervisionReportDetail>(`/supervision/reports/${encodeURIComponent(id)}`, { params: { type }, signal, timeout: 40_000 })).data;
export const fetchSupervisionRules = async (signal?: AbortSignal) =>
  (await apiClient.get<{ rules: PaperLintRule[] }>('/supervision/rules', { signal, timeout: 30_000 })).data.rules;
