import { useEffect, useState, type RefObject } from 'react';
import { announcementRequestId, claimFeedbackAnnouncement } from '../api/announcements';
import { FeedbackAnnouncement } from './FeedbackAnnouncement';

export function AccountAnnouncement({ userId, feedbackTarget }: { userId: string; feedbackTarget: RefObject<HTMLButtonElement | null> }) {
  return <AnnouncementForAccount key={userId} userId={userId} feedbackTarget={feedbackTarget} />;
}

function AnnouncementForAccount({ userId, feedbackTarget }: { userId: string; feedbackTarget: RefObject<HTMLButtonElement | null> }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const requestId = announcementRequestId();
    // Deferring one task lets React StrictMode cancel its probe effect before
    // making a persistent claim. Real unmount/account changes abort any retry.
    const timer = window.setTimeout(() => {
      void claimFeedbackAnnouncement(userId, requestId, controller.signal).then((result) => {
        if (active && result?.show === true) setOpen(true);
      });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [userId]);
  return <FeedbackAnnouncement open={open} onAcknowledge={() => setOpen(false)} feedbackTarget={feedbackTarget} />;
}
