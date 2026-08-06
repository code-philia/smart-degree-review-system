import apiClient from './index';
import type { ReportSubmissionSourceType } from './reportSubmissions';
import type { SupervisorReviewAnnotation, SupervisorReviewFinding } from './reportSupervisorReview';

export type StudentReportResultStatus =
  'submitted_pending_review' | 'review_completed_feedback' | 'student_viewed_feedback';

export type StudentReportResultListFilters = {
  from?: string;
  to?: string;
  source_type?: ReportSubmissionSourceType;
  status?: StudentReportResultStatus;
};

export type StudentReportResultSummary = {
  submission_id: string;
  batch_id: string;
  source_type: ReportSubmissionSourceType;
  report_id: string;
  status: StudentReportResultStatus;
  submitted_at: string;
  feedback_at: string | null;
};

export type StudentReportResultDetail = StudentReportResultSummary & {
  report: {
    title: string;
    original_text: string;
    findings: SupervisorReviewFinding[];
    severity_counts: Record<string, number>;
    created_at: string;
  };
  review: {
    annotations: SupervisorReviewAnnotation[];
    overall_evaluation: string;
    improvement_suggestions: string | null;
    submitted_at: string;
  };
  history_rounds: StudentReportResultSummary[];
};

export type StudentReportResultDownload = {
  submission_id: string;
  report_summary: StudentReportResultSummary;
  annotations: SupervisorReviewAnnotation[];
  overall_evaluation: string;
  improvement_suggestions: string | null;
};

export async function fetchStudentReportResults(
  filters: StudentReportResultListFilters = {},
): Promise<{ results: StudentReportResultSummary[] }> {
  const response = await apiClient.get<{ results: StudentReportResultSummary[] }>('/normative/student-report-results', {
    params: filters,
  });
  return response.data;
}

export async function fetchStudentReportResultDetail(submissionId: string): Promise<StudentReportResultDetail> {
  const response = await apiClient.get<StudentReportResultDetail>(
    `/normative/student-report-results/${encodeURIComponent(submissionId)}`,
  );
  return response.data;
}

export async function downloadStudentReportResultJson(submissionId: string): Promise<StudentReportResultDownload> {
  const response = await apiClient.get<StudentReportResultDownload>(
    `/normative/student-report-results/${encodeURIComponent(submissionId)}/download`,
  );
  return response.data;
}
