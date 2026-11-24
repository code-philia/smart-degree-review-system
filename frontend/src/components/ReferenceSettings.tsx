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
    description: '添加个人 {provider} 密钥，用于参考文献核验。',
    link: '获取 {provider} 密钥',
    label: '{provider} 个人密钥',
    placeholder: '粘贴密钥以保存或替换',
    secure: '密钥按账户加密保存在服务器。',
    configured: '已配置',
    unconfigured: '未配置个人密钥',
    loading: '正在读取配置…',
    unavailable: '安全密钥存储暂不可用。',
    secureTransport: '请通过 HTTPS 安全连接填写密钥。',
    loadError: '配置读取失败，请重试。',
    error: '操作失败，请重试。',
    retry: '重试',
    save: '保存密钥',
    remove: '移除密钥',
    saving: '正在保存…',
    verifying: '正在验证…',
    invalidOpenAlex: 'OpenAlex 密钥无效，请核对后重试。',
    invalidSerpapi: 'SerpAPI 密钥无效，请核对后重试。',
    verificationOpenAlex: '暂时无法验证 OpenAlex 密钥，请稍后重试。',
    verificationSerpapi: '暂时无法验证 SerpAPI 密钥，请稍后重试。',
    removing: '正在移除…',
    saved: '密钥已保存',
    removed: '密钥已移除',
    serpRemove: '移除 SerpAPI 密钥',
  },
  en: {
    title: 'Reference API',
    optional: 'Optional',
    description: 'Add a personal {provider} API key for reference verification.',
    link: 'Get {provider} API key',
    label: '{provider} API key',
    placeholder: 'Paste a key to save or replace it',
    secure: 'Encrypted on the server for your account.',
    configured: 'Configured',
    unconfigured: 'No personal key',
    loading: 'Loading settings…',
    unavailable: 'Secure key storage is temporarily unavailable.',
    secureTransport: 'Use HTTPS to enter API keys.',
    loadError: 'Could not load settings. Please retry.',
    error: 'Could not update settings. Please retry.',
    retry: 'Retry',
    save: 'Save key',
    remove: 'Remove key',
    saving: 'Saving…',
    verifying: 'Verifying…',
    invalidOpenAlex: 'The OpenAlex key is invalid. Check it and try again.',
    invalidSerpapi: 'The SerpAPI key is invalid. Check it and try again.',
    verificationOpenAlex: 'We are temporarily unable to verify the OpenAlex key. Please retry later.',
    verificationSerpapi: 'We are temporarily unable to verify the SerpAPI key. Please retry later.',
    removing: 'Removing…',
    saved: 'Key saved',
    removed: 'Key removed',
    serpRemove: 'Remove SerpAPI key',
  },
};

export function ReferenceSettings({
  userId,
  headingRef,
  showHeading = true,
}: {
  userId: string;
  headingRef?: RefObject<HTMLHeadingElement | null>;
  showHeading?: boolean;
}) {
  // A new account gets a fresh component and no previous secret, hint or request.
  return <ReferenceSettingsForAccount key={userId} userId={userId} headingRef={headingRef} showHeading={showHeading} />;
}

function ReferenceSettingsForAccount({
  userId,
  headingRef,
  showHeading,
}: {
  userId: string;
  headingRef?: RefObject<HTMLHeadingElement | null>;
  showHeading: boolean;
}) {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale);
  const text = copy[locale === 'en' ? 'en' : 'zh'];
  const id = useId();
  const [status, setStatus] = useState<ReferenceSettingsStatus | null>(null);
  const [apiKeys, setApiKeys] = useState({ openalex: '', serpapi: '' });
  const [pendingProvider, setPendingProvider] = useState<ReferenceProvider | null>(null);
  const [operation, setOperation] = useState<'loading' | 'saving' | 'removing' | null>('loading');
  const [message, setMessage] = useState<'saved' | 'removed' | null>(null);
  const [error, setError] = useState<'loadError' | 'error' | 'invalidOpenAlex' | 'invalidSerpapi' | 'verificationOpenAlex' | 'verificationSerpapi' | null>(null);
  const [errorProvider, setErrorProvider] = useState<ReferenceProvider | null>(null);
  const [retry, setRetry] = useState(0);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    setOperation('loading');
    setError(null);
    setErrorProvider(null);
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
    setErrorProvider(provider);
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
        window.dispatchEvent(new Event('smart-degree:reference-settings-changed'));
      }
    } catch (failure) {
      // Never render server/axios error text: it may include request credentials.
      if (!controller.signal.aborted) {
        const code = (failure as { response?: { data?: { error_code?: unknown } } } | undefined)?.response?.data?.error_code;
        const invalid = provider === 'openalex' ? 'invalid_api_key' : 'invalid_serpapi_key';
        setError(code === invalid ? (provider === 'openalex' ? 'invalidOpenAlex' : 'invalidSerpapi')
          : code === `${provider}_verification_unavailable` ? (provider === 'openalex' ? 'verificationOpenAlex' : 'verificationSerpapi') : 'error');
      }
    } finally {
      if (!controller.signal.aborted) {
        setOperation(null);
        setPendingProvider(null);
      }
    }
  }

  const busy = operation !== null;
  return (
    <section className="reference-settings" aria-labelledby={showHeading ? `${id}-title` : undefined} aria-busy={busy}>
      {showHeading ? <div className="preferences-section-label reference-settings-heading">
        <KeyRound size={17} aria-hidden="true" />
        <h3 id={`${id}-title`} ref={headingRef} tabIndex={-1}>
          {text.title}
        </h3>
        <span className="reference-settings-optional">{text.optional}</span>
      </div> : null}
      <div className="reference-settings-providers">
      {(['openalex', 'serpapi'] as const).map((provider) => {
        const serp = provider === 'serpapi';
        const providerName = serp ? 'SerpAPI' : 'OpenAlex';
        const configured = serp ? status?.serpapi_configured : status?.configured;
        const hint = serp ? status?.serpapi_key_hint : status?.key_hint;
        const saving = pendingProvider === provider && operation === 'saving';
        const removing = pendingProvider === provider && operation === 'removing';
        const providerError = error && errorProvider === provider ? error : null;
        return (
          <fieldset className="reference-settings-provider" key={provider}>
            <legend className="sr-only">{providerName}</legend>
            <div className="reference-settings-provider-heading">
              <h4 aria-hidden="true">{providerName}</h4>
            <div className="reference-settings-key-status" data-configured={Boolean(configured)}>
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
            </div>
            <p className="reference-settings-description">{text.description.replace('{provider}', providerName)}</p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void update(provider);
              }}
            >
              <label htmlFor={`${id}-${provider}-key`} className="reference-settings-label">
                {text.label.replace('{provider}', providerName)}
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
                aria-describedby={`${id}-privacy${providerError ? ` ${id}-${provider}-error` : ''}`}
                aria-invalid={providerError === 'invalidOpenAlex' || providerError === 'invalidSerpapi' || undefined}
                disabled={busy || !status?.storage_available || status.secure_transport_required}
                onChange={(event) => {
                  setApiKeys((values) => ({ ...values, [provider]: event.target.value }));
                  setMessage(null);
                  if (errorProvider === provider) { setError(null); setErrorProvider(null); }
                }}
              />
              <div className="reference-settings-actions">
                <Button
                  type="submit"
                  size="sm"
                  disabled={
                    busy || !status?.storage_available || status.secure_transport_required || !apiKeys[provider].trim()
                  }
                >
                  {saving ? text.verifying : text.save}
                </Button>
              </div>
              {providerError ? <p id={`${id}-${provider}-error`} className="reference-settings-error" role="alert">{text[providerError]}</p> : null}
              <div className="reference-settings-provider-footer">
                <a className="reference-settings-link" href={serp ? 'https://serpapi.com/users/sign_up' : 'https://openalex.org/settings/api'} target="_blank" rel="noopener noreferrer">
                  {text.link.replace('{provider}', providerName)}<ArrowUpRight size={14} aria-hidden="true" />
                </a>
                {configured ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
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
      </div>
      <p id={`${id}-privacy`} className="reference-settings-privacy"><ShieldCheck size={15} aria-hidden="true" />{text.secure}</p>
      {status?.secure_transport_required ? (
        <p className="reference-settings-message">{text.secureTransport}</p>
      ) : status && !status.storage_available ? (
        <p className="reference-settings-message">{text.unavailable}</p>
      ) : null}
      {error === 'loadError' ? (
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
