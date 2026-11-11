import { useSyncExternalStore } from 'react';
import { getLocale, getPresentationRevision, hasTranslation, subscribe, translate } from './locale';
import { preserveText } from './jsx-runtime';

// Generated explanations must not fall back to Chinese in the English report.
// Source evidence and literal corrections keep their existing OriginalText boundaries.
export function ReportProse({ text }: { text?: string | null }) {
  useSyncExternalStore(subscribe, getPresentationRevision, getPresentationRevision);
  if (!text) return null;
  if (getLocale() === 'en' && !hasTranslation(text, 'en')) {
    return <span>English translation is not ready yet.</span>;
  }
  return preserveText(translate(text));
}
