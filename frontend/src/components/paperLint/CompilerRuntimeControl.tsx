import { useEffect, useState } from 'react';
import { isAxiosError } from 'axios';
import { useAuthSession } from '../../auth/AuthSessionProvider';
import { fetchCompilerRuntimeState, setCompilerFreeze, type CompilerRuntimeState } from '../../api/compilerControl';
import { Card, ErrorState, LoadingState } from '../ui';

export function CompilerRuntimeControl() {
  const { user } = useAuthSession();
  const canManage = user?.role === 'SCHOOL_ADMIN' || user?.role === 'COLLEGE_ADMIN';
  const [state, setState] = useState<CompilerRuntimeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!canManage) return;
    let current = true;
    setLoading(true);
    setState(null);
    setError(null);
    fetchCompilerRuntimeState()
      .then(value => { if (current) setState(value); })
      .catch(error => { if (current) setError(isAxiosError(error) && error.response?.status === 503
        ? '自动迭代管理暂未启用，请联系管理员。' : '自动迭代状态暂不可用，请重试。'); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [canManage, user?.id, reload]);

  async function changeFreeze(freeze: boolean) {
    setSaving(true);
    setError(null);
    try { setState(await setCompilerFreeze(freeze)); }
    catch { setError('自动迭代设置未保存，请重试。'); }
    finally { setSaving(false); }
  }

  if (!canManage) return null;
  return <div className="mx-auto mb-6 max-w-7xl"><Card title="自动迭代">
    {loading ? <LoadingState label="正在读取自动迭代状态…" /> : null}
    {state ? <div className="flex flex-wrap items-center justify-between gap-4">
      <div><p className="font-semibold text-slate-900">自动迭代：{state.freeze ? '冻结' : '开启（默认）'}</p>
        <p className="mt-1 text-sm text-slate-600">冻结后继续使用当前版本完成检测。</p></div>
      <label className="flex cursor-pointer items-center gap-3 text-sm font-semibold text-slate-700">
        <input type="checkbox" role="switch" aria-label="冻结自动迭代" checked={state.freeze}
          disabled={saving || loading} onChange={event => void changeFreeze(event.target.checked)}
          className="size-5 accent-brand-600 disabled:cursor-wait" />冻结自动迭代
      </label>
    </div> : null}
    {error ? <div className="mt-3"><ErrorState title="设置未完成" message={error}
      onRetry={!state ? () => setReload(value => value + 1) : undefined} /></div> : null}
  </Card></div>;
}
