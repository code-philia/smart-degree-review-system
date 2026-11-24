/** @jsxImportSource react */
import { useSyncExternalStore } from 'react';
import { KeyRound, LoaderCircle } from 'lucide-react';
import { getLocale, subscribe } from '../../i18n/locale';
import type { ReferenceKeyAccess } from '../../hooks/useReferenceKeyAccess';

export function ReferenceKeyNotice({ id, access, onConfigure, onRetry, onDeselect }: {
  id: string; access?: ReferenceKeyAccess; onConfigure: () => void; onRetry?: () => void; onDeselect: () => void;
}) {
  const en = useSyncExternalStore(subscribe, getLocale, getLocale) === 'en';
  const loading = access?.loading;
  const error = access?.error;
  return <div id={id} role="status" className="mb-4 flex items-start gap-3 rounded-xl border border-border bg-background px-4 py-3.5 text-sm text-foreground">
    {loading ? <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin motion-reduce:animate-none text-muted-foreground" aria-hidden="true" />
      : <KeyRound className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />}
    <div className="min-w-0 flex-1">
      <strong className="font-semibold">{loading ? (en ? 'Checking API key access…' : '正在读取密钥配置…')
        : error ? (en ? 'Unable to check API key access' : '暂时无法读取密钥配置')
          : en ? 'A personal API key is required' : '此规则需要个人密钥'}</strong>
      {!loading ? <>
        <p className="mt-1 leading-6 text-muted-foreground">{error
          ? en ? 'Retry, or deselect this rule to continue with other checks.' : '请重试，或取消此规则后继续使用其他检测规则。'
          : en ? 'Save a valid OpenAlex or SerpAPI key to use this rule, or deselect it to continue with other checks.'
            : '请先保存 OpenAlex 或 SerpAPI 其中一个有效密钥，或取消此规则后继续检测。'}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2">
          <button type="button" className="rounded text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-4" onClick={error ? onRetry : onConfigure}>{error ? en ? 'Retry' : '重试' : en ? 'Configure API key' : '配置密钥'}</button>
          <button type="button" className="rounded text-muted-foreground underline-offset-4 hover:text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-4" onClick={onDeselect}>{en ? 'Deselect this rule' : '取消此规则'}</button>
        </div>
      </> : null}
    </div>
  </div>;
}
