/** @jsxImportSource react */
import { useEffect, useId, useRef, useState, useSyncExternalStore, type RefObject } from 'react';
import { ArrowUpRight, CheckCircle2, KeyRound, Loader2, ShieldCheck } from 'lucide-react';
import { getLocale, subscribe } from '../i18n/locale';
import {
  fetchReferenceSettings,
  removeReferenceKey,
  saveReferenceKey,
  type ReferenceProvider,
  type ReferenceSettingsStatus,
} from '../api/referenceSettings';
import { Button } from './shadcn/button';
import './reference-settings.css';

const copy = {
  zh: {
    title: '参考文献 API',
    optional: '可选',
    description: '添加个人 OpenAlex API Key，用于参考文献核验。',
    fallback: '个人 OpenAlex 密钥 → 平台 OpenAlex 密钥 → Crossref。未配置也可使用；数据源不可用时会尝试后续来源。',
    link: '获取 OpenAlex API Key',
    label: '个人 API Key',
    placeholder: '粘贴密钥以保存或替换',
    secure: '密钥按账户加密保存在服务器，仅显示掩码。',
    configured: '已配置',
    unconfigured: '未配置个人密钥',
    loading: '正在读取配置…',
    unavailable: '安全密钥存储暂不可用。',
    secureTransport: '请通过 HTTPS 安全连接填写 API Key。',
    loadError: '配置读取失败，请重试。',
    error: '操作失败，请重试。',
    retry: '重试',
    save: '保存密钥',
    replace: '替换密钥',
    remove: '移除密钥',
    saving: '正在保存…',
    removing: '正在移除…',
    saved: '密钥已保存',
    removed: '密钥已移除',
    serpDescription: '数据库未能核验时，可选用 SerpAPI 补充搜索，消耗您自己的 SerpAPI 配额。',
    serpLink: '注册 SerpAPI 并获取密钥',
    serpLabel: 'SerpAPI 个人密钥',
    serpSave: '保存 SerpAPI 密钥',
    serpReplace: '替换 SerpAPI 密钥',
    serpRemove: '移除 SerpAPI 密钥',
  },
  en: {
    title: 'Reference API',
    optional: 'Optional',
    description: 'Add a personal OpenAlex API key for reference verification.',
    fallback:
      'Personal OpenAlex key → platform OpenAlex key → Crossref. You can continue without a key; unavailable sources fall back to the next provider.',
    link: 'Get an OpenAlex API key',
    label: 'Personal API key',
    placeholder: 'Paste a key to save or replace it',
    secure: 'Encrypted on the server for your account. Only a masked hint is shown.',
    configured: 'Configured',
    unconfigured: 'No personal key',
    loading: 'Loading settings…',
    unavailable: 'Secure key storage is temporarily unavailable.',
    secureTransport: 'Use HTTPS to enter API keys.',
    loadError: 'Could not load settings. Please retry.',
    error: 'Could not update settings. Please retry.',
    retry: 'Retry',
    save: 'Save key',
    replace: 'Replace key',
    remove: 'Remove key',
    saving: 'Saving…',
    removing: 'Removing…',
    saved: 'Key saved',
    removed: 'Key removed',
    serpDescription:
      'Optionally use SerpAPI for extra search when database checks are unresolved. This uses your own SerpAPI quota.',
    serpLink: 'Sign up for SerpAPI and get a key',
    serpLabel: 'Personal SerpAPI key',
    serpSave: 'Save SerpAPI key',
    serpReplace: 'Replace SerpAPI key',
    serpRemove: 'Remove SerpAPI key',
  },
};

export function ReferenceSettings({
  userId,
  headingRef,
}: {
  userId: string;
  headingRef?: RefObject<HTMLHeadingElement | null>;
}) {
  // A new account gets a fresh component and no previous secret, hint or request.
  return <ReferenceSettingsForAccount key={userId} userId={userId} headingRef={headingRef} />;
}

function ReferenceSettingsForAccount({
  userId,
  headingRef,
}: {
  userId: string;
  headingRef?: RefObject<HTMLHeadingElement | null>;
}) {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale);
  const text = copy[locale === 'en' ? 'en' : 'zh'];
  const id = useId();
  const [status, setStatus] = useState<ReferenceSettingsStatus | null>(null);
  const [apiKeys, setApiKeys] = useState({ openalex: '', serpapi: '' });
  const [pendingProvider, setPendingProvider] = useState<ReferenceProvider | null>(null);
  const [operation, setOperation] = useState<'loading' | 'saving' | 'removing' | null>('loading');
  const [message, setMessage] = useState<'saved' | 'removed' | null>(null);
  const [error, setError] = useState<'loadError' | 'error' | null>(null);
  const [retry, setRetry] = useState(0);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    setOperation('loading');
    setError(null);
    void fetchReferenceSettings(controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setStatus(next);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('loadError');
      })
      .finally(() => {
        if (!controller.signal.aborted) setOperation(null);
      });
    return () => {
      request.current?.abort();
    };
  }, [retry]);

  async function update(provider: ReferenceProvider, remove = false) {
    if (operation || !status || (!remove && !apiKeys[provider].trim())) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setOperation(remove ? 'removing' : 'saving');
    setPendingProvider(provider);
    setMessage(null);
    setError(null);
    // Clear immediately so a pending request never leaves a visible secret.
    const enteredKey = apiKeys[provider].trim();
    setApiKeys((values) => ({ ...values, [provider]: '' }));
    try {
      const next = remove
        ? await removeReferenceKey(userId, controller.signal, provider)
        : await saveReferenceKey(userId, enteredKey, controller.signal, provider);
      if (!controller.signal.aborted) {
        setStatus(next);
        setMessage(remove ? 'removed' : 'saved');
      }
    } catch {
      // Never render server/axios error text: it may include request credentials.
      if (!controller.signal.aborted) setError('error');
    } finally {
      if (!controller.signal.aborted) {
        setOperation(null);
        setPendingProvider(null);
      }
    }
  }

  const busy = operation !== null;
  return (
    <section className="reference-settings" aria-labelledby={`${id}-title`} aria-busy={busy}>
      <div className="preferences-section-label reference-settings-heading">
        <KeyRound size={17} aria-hidden="true" />
        <h3 id={`${id}-title`} ref={headingRef} tabIndex={-1}>
          {text.title}
        </h3>
        <span className="reference-settings-optional">{text.optional}</span>
      </div>
      {(['openalex', 'serpapi'] as const).map((provider) => {
        const serp = provider === 'serpapi';
        const configured = serp ? status?.serpapi_configured : status?.configured;
        const hint = serp ? status?.serpapi_key_hint : status?.key_hint;
        const saving = pendingProvider === provider && operation === 'saving';
        const removing = pendingProvider === provider && operation === 'removing';
        return (
          <fieldset className="reference-settings-provider" key={provider}>
            <legend>{serp ? 'SerpAPI' : 'OpenAlex'}</legend>
            <p className="reference-settings-description">{serp ? text.serpDescription : text.description}</p>
            {!serp ? (
              <p className="reference-settings-fallback" id={`${id}-fallback`}>
                {text.fallback}
              </p>
            ) : null}
            <a
              className="reference-settings-link"
              href={serp ? 'https://serpapi.com/users/sign_up' : 'https://openalex.org/settings/api'}
              target="_blank"
              rel="noopener noreferrer"
            >
              {serp ? text.serpLink : text.link}
              <ArrowUpRight size={14} aria-hidden="true" />
            </a>
            <div className="reference-settings-key-status">
              {operation === 'loading' ? (
                <>
                  <Loader2 size={14} aria-hidden="true" />
                  {text.loading}
                </>
              ) : status ? (
                <>
                  {configured ? <CheckCircle2 size={14} aria-hidden="true" /> : null}
                  <span>{configured ? text.configured : text.unconfigured}</span>
                  {configured && hint ? <code>{hint}</code> : null}
                </>
              ) : null}
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void update(provider);
              }}
            >
              <label htmlFor={`${id}-${provider}-key`} className="reference-settings-label">
                {serp ? text.serpLabel : text.label}
              </label>
              <input
                id={`${id}-${provider}-key`}
                className="reference-settings-input"
                type="password"
                autoComplete="new-password"
                spellCheck={false}
                autoCapitalize="none"
                value={apiKeys[provider]}
                placeholder={text.placeholder}
                maxLength={512}
                aria-describedby={`${id}-${provider}-privacy${serp ? '' : ` ${id}-fallback`}`}
                disabled={busy || !status?.storage_available || status.secure_transport_required}
                onChange={(event) => {
                  setApiKeys((values) => ({ ...values, [provider]: event.target.value }));
                  setMessage(null);
                }}
              />
              <p id={`${id}-${provider}-privacy`} className="reference-settings-privacy">
                <ShieldCheck size={14} aria-hidden="true" />
                {text.secure}
              </p>
              <div className="reference-settings-actions">
                <Button
                  type="submit"
                  size="sm"
                  disabled={
                    busy || !status?.storage_available || status.secure_transport_required || !apiKeys[provider].trim()
                  }
                >
                  {saving
                    ? text.saving
                    : configured
                      ? serp
                        ? text.serpReplace
                        : text.replace
                      : serp
                        ? text.serpSave
                        : text.save}
                </Button>
                {configured ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => void update(provider, true)}
                  >
                    {removing ? text.removing : serp ? text.serpRemove : text.remove}
                  </Button>
                ) : null}
              </div>
            </form>
          </fieldset>
        );
      })}
      {status?.secure_transport_required ? (
        <p className="reference-settings-message">{text.secureTransport}</p>
      ) : status && !status.storage_available ? (
        <p className="reference-settings-message">{text.unavailable}</p>
      ) : null}
      {error ? (
        <div className="reference-settings-error" role="alert">
          {text[error]}
          {error === 'loadError' ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => setRetry((value) => value + 1)}>
              {text.retry}
            </Button>
          ) : null}
        </div>
      ) : null}
      <p className="reference-settings-success" role="status" aria-live="polite">
        {message ? text[message] : ''}
      </p>
    </section>
  );
}
