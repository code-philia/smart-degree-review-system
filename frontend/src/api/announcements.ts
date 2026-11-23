import apiClient from './index';

type AnnouncementClaim = { announcement_id: string; show: boolean };

export function announcementRequestId() {
  return globalThis.crypto?.randomUUID?.() ?? `notice-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function claimFeedbackAnnouncement(userId: string, requestId: string, signal: AbortSignal): Promise<AnnouncementClaim | null> {
  // A lost response can be retried safely with the same token. Never delay sign-in.
  for (let attempt = 0; attempt < 2 && !signal.aborted; attempt++) {
    try {
      const response = await apiClient.post<AnnouncementClaim>('/auth/announcements/feedback/claim', { request_id: requestId, expected_user_id: userId }, { signal });
      return response.data;
    } catch {
      if (signal.aborted) return null;
    }
  }
  return null;
}
