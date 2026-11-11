import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { NotificationBell } from '../src/components/NotificationBell';
import { setLocale } from '../src/i18n/locale';
import * as api from '../src/api/notifications';
vi.mock('../src/api/notifications', () => ({
  fetchNotifications: vi.fn(),
  markNotificationsRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));
const filename = '学位论文_一个需要完整显示而不能被省略或翻译的检测文件名_2026.pdf';
const item = {
  id: 'report_ready:a',
  kind: 'report_ready' as const,
  filename,
  createdAt: '2026-11-11T08:00:00.000Z',
  href: '/reports/pdf/a',
  recipient: null,
  read: false,
};
let data: api.NotificationFeed;
function Probe() {
  return <p data-testid="route">{useLocation().pathname}</p>;
}
function view(userId = 'student01') {
  return render(
    <MemoryRouter>
      <NotificationBell userId={userId} />
      <Probe />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  setLocale('zh');
  data = { items: [{ ...item }], unreadCount: 1, total: 1 };
  vi.mocked(api.fetchNotifications).mockImplementation(async () => structuredClone(data));
  vi.mocked(api.markAllNotificationsRead).mockImplementation(async () => {
    data = { ...data, unreadCount: 0, items: data.items.map((x) => ({ ...x, read: true })) };
  });
  vi.mocked(api.markNotificationsRead).mockImplementation(async () => {
    data = { ...data, unreadCount: 0, items: data.items.map((x) => ({ ...x, read: true })) };
  });
});
afterEach(() => {
  cleanup();
  setLocale('zh');
});
it('shows a red unread dot, complete filename and explicit read-all that persists after refresh', async () => {
  const user = userEvent.setup();
  view();
  await waitFor(() => expect(screen.getByRole('button', { name: '通知，有未读消息' })).toBeInTheDocument());
  expect(screen.getByTestId('notification-unread-dot')).toHaveClass('bg-red-500');
  await user.click(screen.getByRole('button', { name: '通知，有未读消息' }));
  expect(await screen.findByText(filename)).toBeVisible();
  expect(screen.getAllByText('1 条未读')).toHaveLength(1);
  expect(api.markAllNotificationsRead).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: '全部已读' }));
  await waitFor(() => expect(screen.queryByTestId('notification-unread-dot')).not.toBeInTheDocument());
  expect(api.markAllNotificationsRead).toHaveBeenCalledOnce();
  act(() => window.dispatchEvent(new Event('focus')));
  await waitFor(() => expect(screen.getByRole('button', { name: '通知' })).toBeInTheDocument());
});
it('switches all event copy to English but preserves the original filename and opens the report', async () => {
  const user = userEvent.setup();
  view();
  await user.click(screen.getByRole('button', { name: /通知/ }));
  await screen.findByText(filename);
  act(() => setLocale('en'));
  expect(screen.getByRole('heading', { name: 'Notifications' })).toBeVisible();
  expect(screen.getByText('Report ready')).toBeVisible();
  expect(screen.getByText(filename)).toBeVisible();
  await user.click(screen.getByRole('link', { name: 'View report' }));
  expect(screen.getByTestId('route')).toHaveTextContent('/reports/pdf/a');
  expect(api.markNotificationsRead).toHaveBeenCalledWith([item.id]);
});
it('does not imply inbox delivery and gives failures a clear next action', async () => {
  data = {
    items: [
      { ...item, id: 'mail_sent:a', kind: 'mail_sent' },
      { ...item, id: 'mail_failed:a', kind: 'mail_failed' },
      { ...item, id: 'detection_failed:b', kind: 'detection_failed', href: '/paper-upload' },
    ],
    unreadCount: 3,
    total: 3,
  };
  setLocale('en');
  const user = userEvent.setup();
  view();
  await user.click(screen.getByRole('button', { name: /Notifications/ }));
  expect(await screen.findByText('Report email sent')).toBeVisible();
  expect(screen.getByText('Delivery may take a little time. You can view the report now.')).toBeVisible();
  expect(screen.getByText('Report email could not be sent')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Return to upload' })).toHaveAttribute('href', '/paper-upload');
});
it('shows a readable empty state and retries errors', async () => {
  vi.mocked(api.fetchNotifications).mockRejectedValueOnce(new Error('offline'));
  const user = userEvent.setup();
  view();
  await screen.findByRole('button', { name: '通知' });
  await user.click(screen.getByRole('button', { name: '通知' }));
  await screen.findByText(filename);
  data = { items: [], unreadCount: 0, total: 0 };
  act(() => window.dispatchEvent(new Event('focus')));
  expect(await screen.findByText('暂无通知')).toBeVisible();
});
it('discards an old account response after switching users', async () => {
  let resolve!: (value: api.NotificationFeed) => void;
  vi.mocked(api.fetchNotifications).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const mounted = view('first');
  data = { items: [], unreadCount: 0, total: 0 };
  mounted.rerender(
    <MemoryRouter>
      <NotificationBell userId="second" />
      <Probe />
    </MemoryRouter>,
  );
  await waitFor(() => expect(api.fetchNotifications).toHaveBeenCalledTimes(2));
  await act(async () => resolve({ items: [item], unreadCount: 1, total: 1 }));
  await userEvent.click(screen.getByRole('button', { name: '通知' }));
  expect(await screen.findByText('暂无通知')).toBeVisible();
  expect(screen.queryByText(filename)).not.toBeInTheDocument();
});
it('keeps a read action authoritative when an older refresh returns late', async () => {
  const user = userEvent.setup();
  view();
  await waitFor(() => expect(screen.getByTestId('notification-unread-dot')).toBeInTheDocument());
  await user.click(screen.getByRole('button', { name: '通知，有未读消息' }));
  await screen.findByText(filename);
  let resolve!: (value: api.NotificationFeed) => void;
  vi.mocked(api.fetchNotifications).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  act(() => window.dispatchEvent(new Event('focus')));
  await user.click(screen.getByRole('button', { name: '全部已读' }));
  await waitFor(() => expect(screen.queryByTestId('notification-unread-dot')).not.toBeInTheDocument());
  await act(async () => resolve({ items: [item], unreadCount: 1, total: 1 }));
  expect(screen.queryByTestId('notification-unread-dot')).not.toBeInTheDocument();
});
it('offers a real reload when loading fails and does not mark failed writes read', async () => {
  vi.mocked(api.fetchNotifications).mockRejectedValue(new Error('offline'));
  const user = userEvent.setup();
  view();
  await user.click(screen.getByRole('button', { name: '通知' }));
  expect(await screen.findByText('通知暂时无法加载')).toBeVisible();
  vi.mocked(api.fetchNotifications).mockImplementation(async () => structuredClone(data));
  await user.click(screen.getByRole('button', { name: '重试' }));
  expect(await screen.findByText(filename)).toBeVisible();
  vi.mocked(api.markAllNotificationsRead).mockRejectedValue(new Error('offline'));
  await user.click(screen.getByRole('button', { name: '全部已读' }));
  expect(await screen.findByText('已读状态未保存，请重试。')).toBeVisible();
  expect(screen.getByTestId('notification-unread-dot')).toBeInTheDocument();
  vi.mocked(api.markAllNotificationsRead).mockImplementation(async () => {
    data = { ...data, unreadCount: 0, items: data.items.map((x) => ({ ...x, read: true })) };
  });
  await user.click(screen.getByRole('button', { name: '重试' }));
  await waitFor(() => expect(api.markAllNotificationsRead).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.queryByTestId('notification-unread-dot')).not.toBeInTheDocument());
});
