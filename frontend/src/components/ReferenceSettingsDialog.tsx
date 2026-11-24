import { useRef, useSyncExternalStore, type ComponentProps } from 'react';
import { KeyRound, X } from 'lucide-react';
import { getLocale, subscribe } from '../i18n/locale';
import { preserveText } from '../i18n/jsx-runtime';
import { Dialog, DialogClose, DialogContent, DialogHeader, DialogTitle } from './shadcn/dialog';
import { Button } from './shadcn/button';
import { ReferenceSettings } from './ReferenceSettings';

export function ReferenceSettingsDialog({ open, onOpenChange, onCloseAutoFocus, userId }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCloseAutoFocus?: ComponentProps<typeof DialogContent>['onCloseAutoFocus'];
  userId?: string;
}) {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale);
  const heading = useRef<HTMLHeadingElement>(null);
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent showCloseButton={false} aria-describedby={undefined}
      className="reference-api-dialog flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-[600px]"
      onCloseAutoFocus={onCloseAutoFocus}
      onOpenAutoFocus={event => { event.preventDefault(); heading.current?.focus(); }}>
      <DialogHeader className="reference-api-header">
        <div className="reference-api-title-row">
          <KeyRound size={21} strokeWidth={1.8} aria-hidden="true" />
          <DialogTitle ref={heading} tabIndex={-1}>{preserveText(locale === 'en' ? 'Reference API' : '参考文献 API')}</DialogTitle>
          <span className="reference-settings-optional">{preserveText(locale === 'en' ? 'Optional' : '可选')}</span>
        </div>
        <DialogClose asChild><Button type="button" variant="ghost" size="icon-sm" aria-label="关闭"><X size={17} aria-hidden="true" /></Button></DialogClose>
      </DialogHeader>
      <div className="reference-api-body">
        {open && userId ? <ReferenceSettings userId={userId} showHeading={false} /> : null}
      </div>
    </DialogContent>
  </Dialog>;
}
