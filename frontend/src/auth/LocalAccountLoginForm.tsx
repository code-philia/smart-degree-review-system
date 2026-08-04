import { FormEvent, useState } from 'react';
import { useAuthSession } from './AuthSessionProvider';

function LocalAccountLoginForm() {
  const { login, status, user } = useAuthSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage(null);

    try {
      await login({ username, password });
    } catch {
      setErrorMessage('账号或密码不正确，请重试。');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit} aria-label="本地账号密码登录表单">
      <label className="block">
        <span className="mb-2 block text-sm font-semibold text-slate-700">账号</span>
        <input
          className="h-12 w-full border border-[#D6D6D6] px-4 outline-none focus:border-[#4F7FF0]"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
      </label>
      <label className="block">
        <span className="mb-2 block text-sm font-semibold text-slate-700">密码</span>
        <input
          className="h-12 w-full border border-[#D6D6D6] px-4 outline-none focus:border-[#4F7FF0]"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <button
        className="h-12 w-full bg-[#4F7FF0] font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        type="submit"
        disabled={submitting || status === 'loading'}
      >
        {submitting ? '登录中…' : '登录'}
      </button>
      {errorMessage ? <p className="text-sm font-semibold text-red-600">{errorMessage}</p> : null}
      {user ? (
        <p className="rounded border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          已登录：{user.username}（{user.role}）
        </p>
      ) : null}
    </form>
  );
}

export default LocalAccountLoginForm;
