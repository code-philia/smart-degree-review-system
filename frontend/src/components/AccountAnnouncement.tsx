import { useEffect, useState, type RefObject } from 'react';
import { announcementRequestId, claimFeedbackAnnouncement } from '../api/announcements';
import { FeedbackAnnouncement } from './FeedbackAnnouncement';

type AnnouncementProps = { userId: string; feedbackTarget: RefObject<HTMLButtonElement | null>; onOpenReferenceSettings: () => void };

export function AccountAnnouncement(props: AnnouncementProps) {
  return <AnnouncementForAccount key={props.userId} {...props} />;
}

function AnnouncementForAccount({ userId, feedbackTarget, onOpenReferenceSettings }: AnnouncementProps) {
  const [open, setOpen] = useState(false);
  const [presentation, setPresentation] = useState(0);
  useEffect(() => {
    let active = true;
    let replayed = false;
    const replay = () => { replayed = true; setPresentation(value => value + 1); setOpen(true); };
    window.addEventListener('smart-degree:replay-guide', replay);
    const controller = new AbortController();
    const requestId = announcementRequestId();
    // Deferring one task lets React StrictMode cancel its probe effect before
    // making a persistent claim. Real unmount/account changes abort any retry.
    const timer = window.setTimeout(() => {
      void claimFeedbackAnnouncement(userId, requestId, controller.signal).then((result) => {
        if (active && !replayed && result?.show === true) setOpen(true);
      });
    }, 0);
    return () => { active = false; window.removeEventListener('smart-degree:replay-guide', replay); window.clearTimeout(timer); controller.abort(); };
  }, [userId]);
  return <FeedbackAnnouncement key={presentation} open={open} onAcknowledge={() => setOpen(false)} feedbackTarget={feedbackTarget} onOpenReferenceSettings={onOpenReferenceSettings} />;
}
