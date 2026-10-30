import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { submitSystemFeedback } from '../api/feedback';
import { Button } from './shadcn/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from './shadcn/dialog';

const areas = [
  ['detection_accuracy', '检测准确性'], ['ai_suggestion_quality', 'AI 建议质量'],
  ['pdf_location', 'PDF 定位'], ['system_stability', '系统稳定性'],
  ['page_design', '页面设计'], ['other', '其他'],
];

function newFeedbackRequestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  return `feedback-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function SystemFeedbackDialog() {
  const [open, setOpen] = useState(false);
  const [score, setScore] = useState(0);
  const [selectedAreas, setSelectedAreas] = useState<string[]>([]);
  const [comment, setComment] = useState('');
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  function reset() { setScore(0); setSelectedAreas([]); setComment(''); setMessage(null); setError(null); }
  function close(next: boolean) { if (!next && !pending) { setOpen(false); reset(); } else setOpen(next); }
  async function submit() {
    if (!score) { setError('请先选择满意度'); return; }
    setPending(true); setError(null);
    try { await submitSystemFeedback({ satisfaction_score: score, improvement_areas: selectedAreas, comment: comment || undefined, request_id: newFeedbackRequestId() }); setMessage('感谢反馈！'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '提交失败，请稍后重试'); }
    finally { setPending(false); }
  }
  return <Dialog open={open} onOpenChange={close}>
    <DialogTrigger asChild><Button variant="ghost" size="sm" className="shrink-0"><MessageSquare className="size-4" />使用反馈</Button></DialogTrigger>
    <DialogContent>
      <DialogHeader><DialogTitle>使用反馈</DialogTitle><DialogDescription>帮助我们改进论文规则检测和 修复建议。</DialogDescription></DialogHeader>
      {message ? <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p> : <>
        <fieldset><legend className="text-sm font-semibold">整体满意度（必选）</legend><div className="mt-2 flex gap-2" role="radiogroup" aria-label="整体满意度">{[1, 2, 3, 4, 5].map((value) => <label key={value} className={`flex size-9 cursor-pointer items-center justify-center rounded-lg border text-sm font-semibold ${score === value ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background hover:bg-muted'}`}><input className="sr-only" type="radio" name="satisfaction-score" value={value} checked={score === value} onChange={() => setScore(value)} />{value}</label>)}</div></fieldset>
        <fieldset><legend className="text-sm font-semibold">希望改进的方面（可多选）</legend><div className="mt-2 grid grid-cols-2 gap-2 text-sm">{areas.map(([value, label]) => <label key={value} className="flex items-center gap-2"><input type="checkbox" checked={selectedAreas.includes(value)} onChange={() => setSelectedAreas((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value])} />{label}</label>)}</div></fieldset>
        <label className="text-sm font-semibold">补充意见（可选）<textarea className="mt-2 min-h-20 w-full rounded-md border border-slate-200 p-2 font-normal" value={comment} onChange={(event) => setComment(event.target.value)} /></label>
        {error ? <p className="text-sm text-red-600" role="alert">{error}</p> : null}
        <DialogFooter><Button type="button" variant="outline" onClick={() => close(false)}>取消</Button><Button type="button" disabled={pending} onClick={() => void submit()}>{pending ? '提交中…' : '提交反馈'}</Button></DialogFooter>
      </>}
    </DialogContent>
  </Dialog>;
}
