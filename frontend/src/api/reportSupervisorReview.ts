import apiClient from './index';
import type { ReportSubmissionSourceType } from './reportSubmissions';
import type { NormativeIssue } from './normativeRules';

export type SupervisorReviewStatus = 'submitted_pending_review' | 'review_completed_feedback';

export type SupervisorReviewFinding = NormativeIssue & {
  finding_id: string;
  source?: string;
};

export type SupervisorReviewAnnotation = {
  finding_id: string;
  comment: string;
};

export type SupervisorReviewDetailResponse = {
  submission_id: string;
  todo_id: string;
  student_id: string;
  assignee_id: string;
  source_type: ReportSubmissionSourceType;
  report_id: string;
  status: SupervisorReviewStatus;
  todo_status: 'pending' | 'done';
  report: {
    title: string;
    original_text: string;
    findings: SupervisorReviewFinding[];
    severity_counts: Record<string, number>;
    created_at: string;
  };
  review: {
    locked: boolean;
    annotations: SupervisorReviewAnnotation[];
    overall_evaluation: string | null;
    improvement_suggestions: string | null;
    submitted_at: string | null;
  };
};

export type SubmitSupervisorReviewRequest = {
  annotations: SupervisorReviewAnnotation[];
  overall_evaluation: string;
  improvement_suggestions?: string;
};

export type SubmitSupervisorReviewResponse = SupervisorReviewDetailResponse & {
  status: 'review_completed_feedback';
  todo_status: 'done';
};

export async function fetchSupervisorReviewDetail(submissionId: string): Promise<SupervisorReviewDetailResponse> {
  const response = await apiClient.get<SupervisorReviewDetailResponse>(
    `/normative/supervisor-review-queue/${encodeURIComponent(submissionId)}`,
  );
  return response.data;
}

export async function submitSupervisorReview(
  submissionId: string,
  payload: SubmitSupervisorReviewRequest,
): Promise<SubmitSupervisorReviewResponse> {
  const response = await apiClient.post<SubmitSupervisorReviewResponse>(
    `/normative/supervisor-review-queue/${encodeURIComponent(submissionId)}/review`,
    payload,
  );
  return response.data;
}
