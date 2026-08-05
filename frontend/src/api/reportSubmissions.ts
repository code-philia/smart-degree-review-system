import apiClient from './index';

export type ReportSubmissionSourceType = 'normative' | 'duplication' | 'innovation' | 'ai_review';

export type ReportSubmissionRequestItem = {
  source_type: ReportSubmissionSourceType;
  report_id: string;
};

export type CreateReportSubmissionRequest = {
  reports: ReportSubmissionRequestItem[];
};

export type ReportSubmissionRecord = {
  id: string;
  batch_id: string;
  student_id: string;
  supervisor_id: string;
  source_type: ReportSubmissionSourceType;
  report_id: string;
  status: 'submitted_pending_review';
  created_at: string;
};

export type ReportSubmissionTodo = {
  id: string;
  submission_id: string;
  assignee_id: string;
  actor_id: string;
  status: 'pending';
  title: string;
  created_at: string;
};

export type CreateReportSubmissionResponse = {
  batch_id: string;
  submissions: ReportSubmissionRecord[];
  todos: ReportSubmissionTodo[];
};

export async function createReportSubmissions(
  payload: CreateReportSubmissionRequest,
): Promise<CreateReportSubmissionResponse> {
  const response = await apiClient.post<CreateReportSubmissionResponse>('/normative/report-submissions', payload);
  return response.data;
}
