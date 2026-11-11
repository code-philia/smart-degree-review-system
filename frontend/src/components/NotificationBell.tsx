import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import {
  Bell,
  BellRing,
  CheckCheck,
  FileCheck2,
  FileUp,
  Mail,
  MailWarning,
  ArrowUpRight,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  fetchNotifications,
  markNotificationsRead,
  markAllNotificationsRead,
  type AppNotification,
  type NotificationFeed,
} from '../api/notifications';
import { getLocale, subscribe } from '../i18n/locale';
import { preserveText } from '../i18n/jsx-runtime';
import { Button } from './shadcn/button';
import { Popover, PopoverContent, PopoverTrigger } from './shadcn/popover';

const copy = {
  zh: {
    title: '通知',
    unreadLabel: '通知，有未读消息',
    readAll: '全部已读',
    empty: '暂无通知',
    emptyNote: '报告完成和邮件发送后，会在这里提醒你。',
    loading: '正在加载通知…',
    error: '通知暂时无法加载',
    readError: '已读状态未保存，请重试。',
    retry: '重试',
    view: '查看报告',
    upload: '返回上传页',
    recent: '显示最近 25 条通知',
    unread: (n: number) => `${n} 条未读`,
    report_ready: ['报告已完成', '检测已完成，可以查看完整报告。'],
    mail_sent: ['报告邮件已发送', '邮件送达可能需要一点时间，你也可以直接查看报告。'],
    detection_failed: ['检测未能完成', '本次检测未完成，请返回上传页重试。'],
    mail_failed: ['报告邮件发送失败', '报告已保存，请直接在网站查看。'],
  },
  en: {
    title: 'Notifications',
    unreadLabel: 'Notifications, unread updates',
    readAll: 'Mark all read',
    empty: 'No notifications yet',
    emptyNote: 'Report and email updates will appear here.',
    loading: 'Loading notifications…',
    error: 'Notifications are unavailable',
    readError: 'Read status was not saved. Please retry.',
    retry: 'Retry',
    view: 'View report',
    upload: 'Return to upload',
    recent: 'Showing the latest 25 notifications',
    unread: (n: number) => `${n} unread`,
    report_ready: ['Report ready', 'The review is complete. View your report.'],
    mail_sent: ['Report email sent', 'Delivery may take a little time. You can view the report now.'],
    detection_failed: ['Review could not be completed', 'Return to the upload page to try again.'],
    mail_failed: ['Report email could not be sent', 'Your report is saved. You can view it here.'],
  },
};
const styles = {
  report_ready: { Icon: FileCheck2, className: 'bg-blue-50 text-blue-600 dark:bg-blue-400/10 dark:text-blue-300' },
  mail_sent: { Icon: Mail, className: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-300' },
  detection_failed: {
    Icon: AlertCircle,
    className: 'bg-amber-50 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300',
  },
  mail_failed: { Icon: MailWarning, className: 'bg-amber-50 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300' },
};

// Remount on account change so no request or unread state can cross accounts.
export function NotificationBell({ userId }: { userId: string }) {
  return <NotificationBellContent key={userId} />;
}
function NotificationBellContent() {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale) as 'zh' | 'en';
  const t = copy[locale];
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [feed, setFeed] = useState<NotificationFeed | null>(null);
  const [error, setError] = useState(false);
  const [readError, setReadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const active = useRef(false),
    sequence = useRef(0),
    mutating = useRef(false);
  const lastRead = useRef<AppNotification | undefined>(undefined);
  const refresh = useCallback(async () => {
    if (mutating.current) return;
    const version = ++sequence.current;
    try {
      const next = await fetchNotifications();
      if (active.current && version === sequence.current) {
        setFeed(next);
        setError(false);
      }
    } catch {
      if (active.current && version === sequence.current) setError(true);
    }
  }, []);
  useEffect(() => {
    active.current = true;
    void refresh();
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh();
    };
    const timer = window.setInterval(onVisible, 30000);
    window.addEventListener('focus', onVisible);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      active.current = false;
      sequence.current++;
      window.clearInterval(timer);
      window.removeEventListener('focus', onVisible);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refresh]);
  async function read(item?: AppNotification) {
    if (mutating.current || item?.read) return;
    mutating.current = true;
    lastRead.current = item;
    sequence.current++;
    setSaving(true);
    setReadError(false);
    try {
      if (item) await markNotificationsRead([item.id]);
      else await markAllNotificationsRead();
      if (active.current)
        setFeed((current) =>
          current
            ? {
                ...current,
                unreadCount: item
                  ? Math.max(0, current.unreadCount - (current.items.some((x) => x.id === item.id && !x.read) ? 1 : 0))
                  : 0,
                items: current.items.map((x) => (!item || x.id === item.id ? { ...x, read: true } : x)),
              }
            : current,
        );
    } catch {
      if (active.current) setReadError(true);
    } finally {
      mutating.current = false;
      if (active.current) {
        setSaving(false);
        void refresh();
      }
    }
  }
  const unread = (feed?.unreadCount || 0) > 0;
  function timestamp(value: string) {
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? ''
      : new Intl.DateTimeFormat(locale === 'en' ? 'en-GB' : 'zh-CN', {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }).format(date);
  }
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void refresh();
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-lg"
          className="relative shrink-0 rounded-xl text-foreground/80"
          aria-label={unread ? t.unreadLabel : t.title}
          title={t.title}
        >
          <Bell className="size-[18px]" strokeWidth={1.8} aria-hidden="true" />
          {unread ? (
            <span
              data-testid="notification-unread-dot"
              aria-hidden="true"
              className="absolute top-1.5 right-1.5 size-2 rounded-full bg-red-500 ring-2 ring-background"
            />
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={12}
        collisionPadding={12}
        aria-labelledby={titleId}
        className="w-[min(420px,calc(100vw-24px))] gap-0 overflow-hidden rounded-2xl border border-border p-0 shadow-xl ring-0"
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4 max-[380px]:gap-2 max-[380px]:px-3">
          <div className="flex min-w-0 items-center gap-2">
            <h2 id={titleId} className="text-base font-semibold text-foreground">
              {t.title}
            </h2>
            {unread ? (
              <span
                title={t.unread(feed!.unreadCount)}
                aria-label={t.unread(feed!.unreadCount)}
                className="whitespace-nowrap rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
              >
                <span className={locale === 'en' ? 'max-[380px]:hidden' : undefined}>
                  {preserveText(t.unread(feed!.unreadCount))}
                </span>
                {locale === 'en' ? (
                  <span aria-hidden="true" className="hidden max-[380px]:inline">
                    {feed!.unreadCount > 99 ? '99+' : feed!.unreadCount}
                  </span>
                ) : null}
              </span>
            ) : null}
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={!unread || saving}
            onClick={() => void read()}
            className="h-8 shrink-0 gap-1.5 px-2 text-[13px] text-primary"
          >
            <CheckCheck className="size-3.5 max-[380px]:hidden" aria-hidden="true" />
            {t.readAll}
          </Button>
        </div>
        {error || readError ? (
          <div
            role="status"
            className="flex items-center justify-between gap-3 border-b border-border bg-muted/40 px-5 py-3 text-sm text-muted-foreground"
          >
            <span>{readError ? t.readError : t.error}</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={saving}
              onClick={() => {
                if (readError) void read(lastRead.current);
                else void refresh();
              }}
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              {t.retry}
            </Button>
          </div>
        ) : null}
        <div
          className="max-h-[min(460px,calc(100dvh-180px))] overflow-y-auto overscroll-contain"
          aria-busy={!feed && !error}
        >
          {!feed && !error ? (
            <p role="status" className="px-5 py-10 text-center text-sm text-muted-foreground">
              {t.loading}
            </p>
          ) : null}
          {feed?.items.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
              <span className="mb-1 flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <BellRing className="size-5" aria-hidden="true" />
              </span>
              <p className="text-sm font-semibold text-foreground">{t.empty}</p>
              <p className="text-sm leading-6 text-muted-foreground">{t.emptyNote}</p>
            </div>
          ) : null}
          <ul className="divide-y divide-border/70">
            {feed?.items.map((item) => {
              const { Icon, className } = styles[item.kind];
              const [title, note] = t[item.kind];
              return (
                <li key={item.id} className={`px-5 py-4 ${item.read ? '' : 'bg-primary/[0.025]'}`}>
                  <div className="flex gap-3">
                    <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl ${className}`}>
                      <Icon className="size-4" strokeWidth={1.8} aria-hidden="true" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm leading-5 font-semibold text-foreground">{title}</p>
                        {!item.read ? (
                          <span
                            className="size-1.5 shrink-0 rounded-full bg-red-500"
                            aria-label={locale === 'en' ? 'Unread' : '未读'}
                          />
                        ) : null}
                      </div>
                      <p
                        data-notification-filename
                        className="mt-1.5 text-sm leading-6 font-medium break-words text-foreground [overflow-wrap:anywhere]"
                        title={item.filename}
                        data-i18n-original-attributes="title"
                      >
                        {preserveText(item.filename)}
                      </p>
                      <p className="mt-1 text-pretty text-[13px] leading-[1.65] text-muted-foreground">{note}</p>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
                        <time dateTime={item.createdAt} className="text-xs leading-5 text-muted-foreground">
                          {preserveText(timestamp(item.createdAt))}
                        </time>
                        <Link
                          to={item.href}
                          onClick={() => {
                            void read(item);
                            setOpen(false);
                          }}
                          className="inline-flex items-center gap-1.5 rounded-md text-[13px] leading-5 font-medium whitespace-nowrap text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        >
                          {item.kind === 'detection_failed' ? (
                            <FileUp className="size-3.5" aria-hidden="true" />
                          ) : (
                            <ArrowUpRight className="size-3.5" aria-hidden="true" />
                          )}
                          {item.kind === 'detection_failed' ? t.upload : t.view}
                        </Link>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
        {feed && feed.total > feed.items.length ? (
          <p className="border-t border-border bg-muted/20 px-5 py-2.5 text-xs leading-5 text-muted-foreground">
            {t.recent}
          </p>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
