import apiClient from './index';
export type AppNotification = {
  id: string;
  kind: 'report_ready' | 'mail_sent' | 'detection_failed' | 'mail_failed';
  filename: string;
  createdAt: string;
  href: string;
  read: boolean;
  recipient: string | null;
};
export type NotificationFeed = { items: AppNotification[]; unreadCount: number; total: number };
export async function fetchNotifications(): Promise<NotificationFeed> {
  return (await apiClient.get<NotificationFeed>('/notifications')).data;
}
export async function markNotificationsRead(ids: string[]): Promise<void> {
  await apiClient.post('/notifications/read', { ids });
}
export async function markAllNotificationsRead(): Promise<void> {
  await apiClient.post('/notifications/read-all', {});
}
