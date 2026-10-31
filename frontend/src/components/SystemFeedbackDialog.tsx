import { useId, useRef, useState } from 'react';
import { CheckCircle2, LoaderCircle, MessageSquare, Star } from 'lucide-react';
import { submitSystemFeedback } from '../api/feedback';
import { Button } from './shadcn/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from './shadcn/dialog';

const areas = [
  ['detection_accuracy', '检测准确性'],
  ['ai_suggestion_quality', 'AI 建议质量'],
  ['pdf_location', 'PDF 定位'],
  ['system_response_speed', '系统响应速度'],
  ['system_stability', '系统稳定性'],
  ['page_design', '页面设计'],
  ['other', '其他'],
];
const satisfactionLabels = ['很不满意', '不太满意', '一般', '满意', '非常满意'];
const maxCommentLength = 1000;

function newFeedbackRequestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  return `feedback-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function SystemFeedbackDialog() {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [score, setScore] = useState(0);
  const [hoveredScore, setHoveredScore] = useState(0);
  const [selectedAreas, setSelectedAreas] = useState<string[]>([]);
  const [comment, setComment] = useState('');
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pendingRef = useRef(false);
  const attemptRef = useRef<{ payload: string; requestId: string } | null>(null);
  function reset() {
    setScore(0);
    setHoveredScore(0);
    setSelectedAreas([]);
    setComment('');
    setMessage(null);
    setError(null);
    attemptRef.current = null;
  }
  function close(next: boolean) {
    if (pendingRef.current) return;
    setOpen(next);
    if (!next) reset();
  }
  async function submit() {
    if (pendingRef.current || message) return;
    if (!score) {
      setError('请先选择满意度');
      return;
    }
    const input = { satisfaction_score: score, improvement_areas: selectedAreas, comment: comment || undefined };
    const payload = JSON.stringify(input);
    if (attemptRef.current?.payload !== payload) {
      attemptRef.current = { payload, requestId: newFeedbackRequestId() };
    }
    pendingRef.current = true;
    setPending(true);
    setError(null);
    try {
      await submitSystemFeedback({ ...input, request_id: attemptRef.current.requestId });
      setMessage('感谢反馈！');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提交失败，请稍后重试');
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="shrink-0">
          <MessageSquare className="size-4" />
          使用反馈
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100dvh-2rem)] gap-6 overflow-y-auto p-6 sm:max-w-xl">
        <DialogHeader className="gap-3 pr-5">
          <DialogTitle className="text-xl font-semibold tracking-tight">使用反馈</DialogTitle>
          <DialogDescription className="leading-relaxed">
            您的反馈将帮助我们优化论文规范性检测和 AI 修复建议
          </DialogDescription>
        </DialogHeader>
        {message ? (
          <div
            className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-700"
            role="status"
          >
            <CheckCircle2 className="size-6 shrink-0" />
            <p className="font-medium">{message}</p>
          </div>
        ) : (
          <>
            <fieldset disabled={pending}>
              <legend id={`${id}-rating-label`} className="text-sm font-semibold">
                整体满意度（必选）
              </legend>
              <div className="mt-3 rounded-xl border border-border bg-muted/30 px-4 py-3">
                <div
                  className="flex items-center gap-2"
                  role="radiogroup"
                  aria-labelledby={`${id}-rating-label`}
                  aria-required="true"
                  onMouseLeave={() => setHoveredScore(0)}
                >
                  {[1, 2, 3, 4, 5].map((value) => (
                    <label
                      key={value}
                      className="relative flex size-11 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-amber-50 focus-within:ring-2 focus-within:ring-primary focus-within:ring-offset-2"
                      onMouseEnter={() => setHoveredScore(value)}
                    >
                      <input
                        className="sr-only"
                        type="radio"
                        name={`${id}-satisfaction-score`}
                        value={value}
                        aria-label={`${value} 星`}
                        required
                        checked={score === value}
                        onChange={() => {
                          setScore(value);
                          setHoveredScore(0);
                          setError(null);
                        }}
                      />
                      <Star
                        aria-hidden="true"
                        className={`size-8 transition-colors ${value <= (hoveredScore || score) ? 'fill-amber-400 text-amber-400' : 'fill-transparent text-slate-300'}`}
                        strokeWidth={1.5}
                      />
                    </label>
                  ))}
                </div>
                <p className="mt-2 min-h-5 text-xs text-muted-foreground" aria-live="polite">
                  {score ? `${score} 星 · ${satisfactionLabels[score - 1]}` : '请选择您的整体使用感受'}
                </p>
              </div>
            </fieldset>
            <fieldset disabled={pending}>
              <legend className="text-sm font-semibold">您希望改进哪些方面（可多选）</legend>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                {areas.map(([value, label]) => (
                  <label
                    key={value}
                    className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 transition-colors ${selectedAreas.includes(value) ? 'border-primary/40 bg-primary/5 text-foreground' : 'border-border hover:bg-muted/60'}`}
                  >
                    <input
                      className="size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                      type="checkbox"
                      checked={selectedAreas.includes(value)}
                      onChange={() =>
                        setSelectedAreas((current) =>
                          current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <div>
              <label htmlFor={`${id}-comment`} className="text-sm font-semibold">
                补充意见（可选）
              </label>
              <textarea
                id={`${id}-comment`}
                className="mt-3 min-h-24 w-full resize-y rounded-xl border border-border bg-background px-3 py-2.5 text-sm leading-relaxed outline-none placeholder:text-muted-foreground/70 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/15 disabled:opacity-60"
                placeholder="欢迎分享您的使用体验或具体建议…"
                value={comment}
                maxLength={maxCommentLength}
                disabled={pending}
                aria-describedby={`${id}-comment-count`}
                onChange={(event) => setComment(event.target.value)}
              />
              <p id={`${id}-comment-count`} className="mt-1 text-right text-xs text-muted-foreground">
                {comment.length}/{maxCommentLength}
              </p>
            </div>
            {error ? (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600" role="alert">
                {error}
              </p>
            ) : null}
          </>
        )}
        <DialogFooter className="-mx-6 -mb-6 flex-col gap-3 bg-muted/30 p-5 sm:flex-col">
          <div className="flex justify-end gap-2">
            {message ? (
              <Button type="button" onClick={() => close(false)}>
                完成
              </Button>
            ) : (
              <>
                <Button type="button" variant="outline" disabled={pending} onClick={() => close(false)}>
                  取消
                </Button>
                <Button type="button" disabled={pending} onClick={() => void submit()}>
                  {pending ? (
                    <>
                      <LoaderCircle className="size-4 animate-spin" />
                      提交中…
                    </>
                  ) : (
                    '提交反馈'
                  )}
                </Button>
              </>
            )}
          </div>
          <p className="text-right text-xs leading-relaxed text-muted-foreground">
            检测结果仅供参考，反馈内容仅用于系统改进
          </p>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
