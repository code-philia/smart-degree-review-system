import { requestedReturnTo } from '../nav/reportLinks';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { ArrowUpRight, LoaderCircle, ShieldCheck, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '../components/shadcn/dialog';
import { REVIEW_ROUTES } from '../nav/reviewRoutes';
import { useAuthSession } from './AuthSessionProvider';

function TrialAccountForm({ pending, setPending }: { pending: boolean; setPending: (value: boolean) => void }) {
  const { loginTrial, status } = useAuthSession();
  const navigate = useNavigate();
  const location = useLocation();
  const id = useId();
  const pendingRef = useRef(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { if (error && !pending) passwordRef.current?.focus(); }, [error, pending]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError('');
    try {
      await loginTrial({ username: username.trim(), password });
      setPassword('');
      navigate(requestedReturnTo(location.state, location.search) || REVIEW_ROUTES.upload, { replace: true });
    } catch (cause) {
      setPassword('');
      setError(cause instanceof Error && /[\u4e00-\u9fff]/.test(cause.message)
        ? cause.message : '登录失败，请稍后重试。');
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  return <>
    <div className="trial-account-mark"><ShieldCheck size={24} aria-hidden="true" /></div>
    <DialogTitle className="trial-account-title">试验账号登录</DialogTitle>
    <DialogDescription className="trial-account-description">使用已分配的试验账号继续。</DialogDescription>
    <DialogClose asChild>
      <button type="button" className="trial-account-close" aria-label="关闭" disabled={pending}><X size={19} /></button>
    </DialogClose>
    <form className="trial-account-form" aria-label="试验账号登录表单" onSubmit={submit}>
      <label htmlFor={`${id}-account`}>账号</label>
      <input id={`${id}-account`} autoFocus autoComplete="username" required maxLength={128}
        value={username} onChange={e => setUsername(e.target.value)} disabled={pending} placeholder="输入账号" />
      <label htmlFor={`${id}-password`}>密码</label>
      <input ref={passwordRef} id={`${id}-password`} type="password" autoComplete="current-password" required maxLength={256}
        value={password} onChange={e => setPassword(e.target.value)} disabled={pending} placeholder="输入密码"
        aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} />
      {error ? <p id={`${id}-error`} className="trial-account-error" role="alert">{error}</p> : null}
      <button className="trial-account-submit" type="submit" disabled={pending || status === 'loading'}>
        {pending ? <><LoaderCircle size={18} className="animate-spin" aria-hidden="true" />登录中…</> : <>登录<ArrowUpRight size={18} aria-hidden="true" /></>}
      </button>
    </form>
  </>;
}

export default function TrialAccountEntry() {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  return <Dialog open={open} onOpenChange={next => { if (!pending) setOpen(next); }}>
    <DialogTrigger asChild>
      <button type="button" className="campus-version">试点验证版 V0.9</button>
    </DialogTrigger>
    {open ? <DialogContent className="trial-account-dialog" showCloseButton={false}>
      <TrialAccountForm pending={pending} setPending={setPending} />
    </DialogContent> : null}
  </Dialog>;
}
