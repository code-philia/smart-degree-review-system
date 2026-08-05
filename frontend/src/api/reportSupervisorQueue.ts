import apiClient from './index';
import type { ReportSubmissionSourceType } from './reportSubmissions';

export type SupervisorReviewTodoStatus = 'pending' | 'done';

export type SupervisorReviewQueueFilters = {
  student_id?: string;
  source_type?: ReportSubmissionSourceType;
  status?: SupervisorReviewTodoStatus;
};

export type SupervisorReviewQueueItem = {
  todo_id: string;
  submission_id: string;
  student_id: string;
  assignee_id: string;
  source_type: ReportSubmissionSourceType;
  report_id: string;
  submission_status: 'submitted_pending_review';
  todo_status: SupervisorReviewTodoStatus;
  title: string;
  created_at: string;
};

export type SupervisorReviewQueueResponse = {
  records: SupervisorReviewQueueItem[];
  unread_count: number;
};

export type SupervisorReviewQueueBadgeResponse = {
  unread_count: number;
};

export async function fetchSupervisorReviewQueue(
  filters: SupervisorReviewQueueFilters = {},
): Promise<SupervisorReviewQueueResponse> {
  const response = await apiClient.get<SupervisorReviewQueueResponse>('/normative/supervisor-review-queue', {
    params: filters,
  });
  return response.data;
}

export async function fetchSupervisorReviewQueueBadge(): Promise<SupervisorReviewQueueBadgeResponse> {
  const response = await apiClient.get<SupervisorReviewQueueBadgeResponse>('/normative/supervisor-review-queue/badge');
  return response.data;
}
