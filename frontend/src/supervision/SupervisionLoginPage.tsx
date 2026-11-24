import { useState, type FormEvent } from 'react';
import { ArrowRight, Files, LockKeyhole, MessageSquareText, ShieldCheck, LoaderCircle } from 'lucide-react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuthSession } from '../auth/AuthSessionProvider';
import './supervision.css';
import { SupervisionThemeButton } from './SupervisionThemeButton';

export default function SupervisionLoginPage() {
  const { user, status, loginSupervision } = useAuthSession();
  const navigate = useNavigate();
  const [username, setUsername] = useState('admin'), [password, setPassword] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  if (status === 'loading') return <div className="sup-session-loading">正在验证管理员身份…</div>;
  if (user?.accessMode === 'supervision') return <Navigate replace to="/admin/reports" />;
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return; setBusy(true); setError('');
    try { await loginSupervision({ username: username.trim(), password }); setPassword(''); navigate('/admin/reports', { replace: true }); }
    catch (cause) { setError(axios.isAxiosError(cause) && typeof cause.response?.data?.message === 'string' ? cause.response.data.message : '登录暂时不可用，请稍后重试'); }
    finally { setBusy(false); }
  }
  return <main className="sup-login">
    <div className="sup-login-appearance"><SupervisionThemeButton /></div>
    <section className="sup-login-story"><Link to="/auth" className="sup-login-brand"><img src="/login-schoolmark.jpg" alt="上海交通大学" />智慧学位</Link><div className="sup-login-story-body"><span className="sup-login-shield"><ShieldCheck size={30} strokeWidth={1.5} /></span><p className="sup-eyebrow">监管工作台</p><h2>全局掌握<br />清晰追溯</h2><p>集中查看全部用户的检测报告与反馈，<br />让每一条意见都有据可查。</p><div className="sup-login-features"><span><Files size={18} />全部检测报告</span><span><MessageSquareText size={18} />全量用户反馈</span></div></div><p className="sup-login-caption">智慧学位 AI 评阅辅助系统</p></section>
    <section className="sup-login-form-side"><div className="sup-login-form-wrap"><span className="sup-login-kicker"><LockKeyhole size={15} />管理员专用入口</span><h1>管理员登录</h1><p className="sup-login-description">登录后进入报告与反馈监管工作台</p>
      <form onSubmit={event => void submit(event)} aria-label="管理员登录表单"><label htmlFor="sup-username">账号</label><input id="sup-username" name="username" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} maxLength={128} required />
        <label htmlFor="sup-password">密码</label><input id="sup-password" name="password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} maxLength={256} required />
        {error ? <p role="alert" className="sup-login-error">{error}</p> : null}
        <button className="sup-login-submit" disabled={busy} type="submit">{busy ? <><LoaderCircle size={18} className="sup-spinning" />正在登录</> : <>登录监管台<ArrowRight size={18} /></>}</button>
      </form><p className="sup-login-footnote"><ShieldCheck size={14} />仅授权管理员可访问监管数据</p><Link className="sup-back-site" to="/auth">返回系统登录页</Link>
    </div></section>
  </main>;
}
