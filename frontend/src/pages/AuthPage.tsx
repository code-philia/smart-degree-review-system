import type { ReactNode } from 'react';
import { ArrowUpRight, BookOpenCheck, ScanLine, PenLine } from 'lucide-react';
import AuthCampusScene from './authCampus/AuthCampusScene';
import './auth-campus.css';

type AuthPageProps = { accountFormSlot?: ReactNode; helpSlot?: ReactNode };

function JaccountEntry() {
  const error = new URLSearchParams(window.location.search).get('jaccount_error');
  const errors: Record<string, string> = {
    state: 'jAccount 登录已过期，请重新登录。',
    provider: 'jAccount 登录暂未完成，请重试。',
    denied: '已取消 jAccount 登录，可重新登录。',
    unavailable: 'jAccount 登录暂不可用，请使用本地账号登录。',
  };
  return (
    <section aria-label="校内账号登录">
      <a href="/api/auth/jaccount" className="jaccount-entry">
        使用 jAccount 登录
        <ArrowUpRight size={18} aria-hidden="true" />
      </a>
      <p className="campus-login-hint">交大师生可使用校内账号统一认证</p>
      {error && typeof errors[error] === 'string' ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {errors[error]}
        </p>
      ) : null}
    </section>
  );
}

function DefaultAccountSlot() {
  return (
    <div className="space-y-4" aria-label="账号登录表单">
      <div className="login-input text-slate-400">请输入账号</div>
      <div className="login-input text-slate-400">请输入密码</div>
    </div>
  );
}

export default function AuthPage({ accountFormSlot, helpSlot }: AuthPageProps) {
  return (
    <main className="campus-signin">
      <AuthCampusScene />
      <header className="campus-header">
        <div className="campus-brand">
          <img src="/brand-mark.jpg" alt="上海交通大学校徽" width="47" height="47" />
          <div>
            <p>
              智慧学位 <span>AI 评阅辅助系统</span>
            </p>
            <span className="campus-brand-en">SMART DEGREE · AI REVIEW</span>
          </div>
        </div>
        <span className="campus-version">
          <i />
          试点验证版 V0.9
        </span>
      </header>
      <div className="campus-content">
        <section className="campus-intro" aria-label="系统检测能力">
          <div className="campus-intro-surface">
            <p>学位论文智能评阅</p>
            <div className="campus-capabilities">
              <span>
                <BookOpenCheck size={21} aria-hidden="true" />
                格式排版
              </span>
              <span>
                <ScanLine size={21} aria-hidden="true" />
                文字表述
              </span>
              <span>
                <PenLine size={21} aria-hidden="true" />
                语言规范
              </span>
            </div>
          </div>
        </section>
        <section className="campus-login" aria-label="身份认证区域">
          <div className="campus-heading">
            <span>欢迎使用</span>
            <h1>统一身份认证</h1>
            <p>登录，开启论文智能审阅</p>
          </div>
          <JaccountEntry />
          <section aria-label="账号密码登录区域">
            <div className="auth-divider">
              <h2>登录本地账号</h2>
            </div>
            {accountFormSlot ?? <DefaultAccountSlot />}
            <div className="campus-help-row">
              <details className="auth-help" id="password">
                <summary>忘记密码 / 用户名</summary>
                <p>如忘记账号或密码，请联系系统管理员重置。交大校内账号请通过 jAccount 官方渠道找回。</p>
              </details>
              {helpSlot ? <div className="auth-demo">{helpSlot}</div> : null}
            </div>
          </section>
          <section className="system-description" aria-label="系统说明">
            <h2>关于本系统</h2>
            <p>
              本系统依托人工智能技术，对照国家标准与学校规范，为学位论文提供格式排版、文字表述、语言规范等自动化检测，并给出修改建议。论文数据均在校内处理，保障信息安全。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议，我们将持续优化。
            </p>
          </section>
        </section>
      </div>
    </main>
  );
}
