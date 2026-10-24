import apiClient from './index';

export type FeedbackValue = 'positive' | 'negative';
export type FindingFeedback = { id: string; feedback_value: FeedbackValue; reason_code: string | null; reason_text: string | null; created_at: string; updated_at: string };
export type SuggestionFeedback = FindingFeedback & { suggestion_id: string; generation: number };

function findingUrl(reportId: string, ruleId: string, findingId: string) {
  return `/normative/feedback/reports/${encodeURIComponent(reportId)}/findings/${encodeURIComponent(ruleId)}/${encodeURIComponent(findingId)}/feedback`;
}
function suggestionUrl(reportId: string, suggestionId: string) {
  return `/normative/feedback/reports/${encodeURIComponent(reportId)}/repair-suggestions/${encodeURIComponent(suggestionId)}/feedback`;
}
type FeedbackInput = { feedback_value: FeedbackValue; reason_code?: string | null; reason_text?: string | null };

export async function fetchFindingFeedback(reportId: string, ruleId: string, findingId: string) {
  return (await apiClient.get<{ feedback: FindingFeedback | null }>(findingUrl(reportId, ruleId, findingId))).data.feedback;
}
export async function saveFindingFeedback(reportId: string, ruleId: string, findingId: string, input: FeedbackInput) {
  return (await apiClient.put<{ feedback: FindingFeedback }>(findingUrl(reportId, ruleId, findingId), input)).data.feedback;
}
export async function deleteFindingFeedback(reportId: string, ruleId: string, findingId: string) {
  await apiClient.delete(findingUrl(reportId, ruleId, findingId));
}
export async function fetchSuggestionFeedback(reportId: string, suggestionId: string) {
  return (await apiClient.get<{ feedback: SuggestionFeedback | null }>(suggestionUrl(reportId, suggestionId))).data.feedback;
}
export async function saveSuggestionFeedback(reportId: string, suggestionId: string, input: FeedbackInput) {
  return (await apiClient.put<{ feedback: SuggestionFeedback }>(suggestionUrl(reportId, suggestionId), input)).data.feedback;
}
export async function deleteSuggestionFeedback(reportId: string, suggestionId: string) {
  await apiClient.delete(suggestionUrl(reportId, suggestionId));
}

export type SystemFeedbackInput = { satisfaction_score: number; improvement_areas: string[]; comment?: string; request_id?: string };
export async function submitSystemFeedback(input: SystemFeedbackInput) {
  return (await apiClient.post<{ id: string; duplicate: boolean }>('/normative/feedback/system-feedback', input)).data;
}
