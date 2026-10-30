import type { ReactNode } from 'react';
import { ArrowUpRight, BookOpenCheck, Pause, Play, ScanLine, Sparkles } from 'lucide-react';
import useAuthCampusScene from './useAuthCampusScene';
import './auth-campus.css';

type AuthPageProps = { accountFormSlot?: ReactNode; helpSlot?: ReactNode };

function HeroPanel() {
  return (
    <section className="auth-hero">
      <p className="auth-eyebrow">
        <span /> 学位论文智能评阅
      </p>
      <h1>
        让研究专注创新，
        <br />
        <em>让论文规范呈现。</em>
      </h1>
      <p className="auth-intro">
        从格式到表达，让每一份学术成果
        <br className="hidden sm:block" />
        都得到更细致的审阅。
      </p>
      <div className="auth-capabilities" aria-label="系统检测能力">
        <span>
          <BookOpenCheck size={17} />
          格式排版
        </span>
        <span>
          <ScanLine size={17} />
          文字表述
        </span>
        <span>
          <Sparkles size={17} />
          语言规范
        </span>
      </div>
    </section>
  );
}

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
  const { imageRef, motionRef, enabled, preference, toggleMotion } = useAuthCampusScene();
  const motionLabel = enabled ? '暂停背景动效' : '开启轻微视差';
  return (
    <main className="auth-page auth-campus-login" data-motion={preference}>
      <div className="auth-campus-scene" aria-hidden="true">
        <div className="auth-photo-motion" ref={motionRef}>
          <img ref={imageRef} src="/sjtu-siyuan-monument.jpg" alt="" width="2048" height="1397" fetchPriority="high" />
        </div>
      </div>
      <div className="auth-container">
        <header className="auth-brand">
          <div className="auth-brand-lockup">
            <img src="/brand-mark.jpg" alt="上海交通大学校徽" width="43" height="43" />
            <div>
              <p>
                智慧学位 <span>AI 评阅辅助系统</span>
              </p>
              <span className="auth-brand-en">SMART DEGREE · AI REVIEW</span>
            </div>
          </div>
          <div className="auth-header-actions">
            <button
              className="auth-motion-toggle"
              type="button"
              onClick={toggleMotion}
              aria-label={motionLabel}
              aria-pressed={enabled}
              title={motionLabel}
            >
              {enabled ? <Pause size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
              <span>{enabled ? '轻微视差' : '开启视差'}</span>
            </button>
            <span className="pilot-badge">
              <span /> 试点验证版 V0.9
            </span>
          </div>
        </header>
        <div className="auth-layout">
          <HeroPanel />
          <section className="auth-card" aria-label="身份认证区域">
            <div className="auth-card-heading">
              <span className="auth-welcome">欢迎使用</span>
              <h2>统一身份认证</h2>
              <p>登录，开启论文智能审阅</p>
            </div>
            <JaccountEntry />
            <section aria-label="账号密码登录区域">
              <div className="auth-divider">
                <h3>登录本地账号</h3>
              </div>
              {accountFormSlot ?? <DefaultAccountSlot />}
              <details className="auth-help" id="password">
                <summary>忘记密码/用户名</summary>
                <p>如忘记账号或密码，请联系系统管理员重置。试点阶段可直接使用下方试用账号登录体验。</p>
              </details>
              {helpSlot ? <div className="auth-demo">{helpSlot}</div> : null}
            </section>
            <section className="system-description" aria-label="系统说明">
              <h2>关于本系统</h2>
              <p>
                本系统依托人工智能技术，对照国家标准与学校规范，为学位论文提供格式排版、文字表述、语言规范等自动化检测，并给出修改建议。论文数据均在校内处理，保障信息安全。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议，我们将持续优化。
              </p>
            </section>
          </section>
        </div>
      </div>
    </main>
  );
}
