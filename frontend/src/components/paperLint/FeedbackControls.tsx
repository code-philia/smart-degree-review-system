import { CheckCircle2, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { FindingFeedback, SuggestionFeedback } from '../../api/feedback';
import { Button } from '../ui';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../shadcn/dialog';

export type FeedbackControlsProps = {
  label: string;
  feedback?: FindingFeedback | SuggestionFeedback | null;
  reasons: [string, string][];
  onValue: (value: 'positive' | 'negative') => void | Promise<void>;
  onReason?: (code: string | null, text: string | null) => void | Promise<void>;
  onCancel: () => void | Promise<void>;
};

export function FeedbackControls({ label, feedback, reasons, onValue, onReason, onCancel }: FeedbackControlsProps) {
  const [reasonCode, setReasonCode] = useState(feedback?.reason_code || '');
  const [reasonText, setReasonText] = useState(feedback?.reason_text || '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [successOpen, setSuccessOpen] = useState(false);
  const pendingRef = useRef(false);
  const submitButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setReasonCode(feedback?.reason_code || '');
    setReasonText(feedback?.reason_text || '');
  }, [feedback?.id, feedback?.reason_code, feedback?.reason_text]);

  async function runAction(action: () => void | Promise<void>, showSuccess = false) {
    // The ref also guards two clicks before React renders the disabled state.
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError('');
    try {
      await action();
      if (showSuccess) setSuccessOpen(true);
    } catch (failure) {
      setError(failure instanceof Error && failure.message ? failure.message : '反馈提交失败，请稍后重试。');
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  return (
    <div
      className="mt-3 rounded-lg border border-slate-100 bg-slate-50 p-2"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      onKeyUp={(event) => event.stopPropagation()}
      aria-busy={pending}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">{label}</span>
        <Button
          size="sm"
          variant="ghost"
          disabled={pending}
          className={
            feedback?.feedback_value === 'positive'
              ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300 hover:bg-emerald-200'
              : ''
          }
          aria-label="有帮助"
          aria-pressed={feedback?.feedback_value === 'positive'}
          onClick={() => void runAction(() => onValue('positive'))}
        >
          <ThumbsUp className="size-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={pending}
          className={
            feedback?.feedback_value === 'negative'
              ? 'bg-red-100 text-red-700 ring-1 ring-red-300 hover:bg-red-200'
              : ''
          }
          aria-label="需要改进"
          aria-pressed={feedback?.feedback_value === 'negative'}
          onClick={() => void runAction(() => onValue('negative'))}
        >
          <ThumbsDown className="size-3.5" />
        </Button>
        {feedback ? (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto text-xs"
            disabled={pending}
            onClick={() => void runAction(onCancel)}
          >
            取消评价
          </Button>
        ) : null}
      </div>
      {feedback?.feedback_value === 'negative' ? (
        <div className="mt-2 space-y-2">
          <select
            aria-label="负面反馈原因"
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-xs"
            disabled={pending}
            value={reasonCode}
            onChange={(event) => setReasonCode(event.target.value)}
          >
            <option value="">可选：选择原因</option>
            {reasons.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
          <textarea
            aria-label="反馈补充说明"
            className="min-h-12 w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-xs"
            placeholder="可选补充说明"
            maxLength={1000}
            disabled={pending}
            value={reasonText}
            onChange={(event) => setReasonText(event.target.value)}
          />
          <Button
            size="sm"
            variant="ghost"
            disabled={pending || !onReason}
            onClick={(event) => {
              if (!onReason) return;
              submitButtonRef.current = event.currentTarget;
              void runAction(() => onReason(reasonCode || null, reasonText || null), true);
            }}
          >
            {pending ? '提交中…' : '提交反馈'}
          </Button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {error}
        </p>
      ) : null}
      <Dialog open={successOpen} onOpenChange={setSuccessOpen}>
        <DialogContent
          showCloseButton={false}
          className="max-w-[calc(100%-2rem)] items-center justify-items-center gap-3 bg-white p-6 text-center text-slate-900 sm:max-w-xs"
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
          onKeyUp={(event) => event.stopPropagation()}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            submitButtonRef.current?.focus();
          }}
        >
          <CheckCircle2 className="size-10 text-emerald-600" aria-hidden="true" />
          <DialogTitle className="text-lg font-semibold">提交成功</DialogTitle>
          <DialogDescription className="text-sm text-slate-500">感谢你的反馈。</DialogDescription>
          <Button size="sm" className="mt-1 min-w-24" onClick={() => setSuccessOpen(false)}>
            知道了
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
