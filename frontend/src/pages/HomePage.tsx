import { Link } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import type { AuthRole } from '../api/authSession';

type ModuleLink = {
  title: string;
  description: string;
  to: string;
  roles?: AuthRole[];
  tag: string;
  metric: string;
};

const roleLabels: Record<AuthRole, string> = {
  STUDENT: '学生端',
  SUPERVISOR: '导师端',
  COLLEGE_ADMIN: '学院端',
  SCHOOL_ADMIN: '学校端',
};

const roleNotes: Record<AuthRole, string> = {
  STUDENT: '提交论文文本、生成检测报告，并推送给本地导师批阅。',
  SUPERVISOR: '查看名下学生检测台账、处理站内待批阅任务。',
  COLLEGE_ADMIN: '维护本学院规则覆盖，查看学院范围质量与检测数据。',
  SCHOOL_ADMIN: '维护全校规则和本地样本库，查看全校统计数据。',
};

const primaryModules: Record<AuthRole, ModuleLink[]> = {
  STUDENT: [
    {
      title: '发起规范性检测',
      description: '上传或粘贴 .txt/.md 论文文本，按当前生效规则生成问题列表。',
      to: '/normative-check',
      tag: '规范',
      metric: '行列定位',
    },
    {
      title: '本地相似度与写作风险',
      description: '使用学校管理员导入的本地样本库计算相似段落和启发式风险分。',
      to: '/duplication-detect',
      tag: '查重',
      metric: '5-gram Jaccard',
    },
    {
      title: '创新性量表评估',
      description: '按硕士/博士五维度量表录入证据、计算综合创新参考分。',
      to: '/innovation-assessment',
      tag: '创新',
      metric: '五维评分',
    },
    {
      title: '规则化辅助评阅',
      description: '选择评阅模板，检查章节、参考文献和规范问题，生成客观评分。',
      to: '/ai-review',
      tag: '评阅',
      metric: '模板评分',
    },
    {
      title: '论文润色',
      description: '生成整篇润色结果，或对局部文本进行可追溯修改建议。',
      to: '/whole-polish',
      tag: '润色',
      metric: '规则改写',
    },
    {
      title: '提交报告给导师',
      description: '选择本人已完成报告，创建站内提交记录和导师待办。',
      to: '/student-report-submissions',
      tag: '提交',
      metric: '批阅流转',
    },
  ],
  SUPERVISOR: [
    {
      title: '导师待批阅中心',
      description: '查看分配给本人的站内待办，进入报告详情并提交反馈。',
      to: '/supervisor-review-queue',
      tag: '批阅',
      metric: '待办队列',
    },
    {
      title: '检测记录台账',
      description: '按导师数据范围查看学生各类检测记录和核心结果。',
      to: '/ledger-records',
      tag: '台账',
      metric: '范围过滤',
    },
    {
      title: '检测统计',
      description: '查看记录数、学生数、今日数量和本地生成趋势图。',
      to: '/ledger-stats',
      tag: '统计',
      metric: '本地图表',
    },
    {
      title: '质量仪表盘',
      description: '聚合规范分、原创参考分、创新参考分和评阅基础分。',
      to: '/quality-dashboard',
      tag: '质量',
      metric: '四项指标',
    },
  ],
  COLLEGE_ADMIN: [
    {
      title: '学院规则配置',
      description: '维护本学院规则覆盖，规则优先级高于学校默认规则。',
      to: '/rule-config',
      tag: '规则',
      metric: '学院覆盖',
    },
    {
      title: '检测记录台账',
      description: '查看本学院范围内的规范、查重、润色、创新和评阅记录。',
      to: '/ledger-records',
      tag: '台账',
      metric: '学院范围',
    },
    {
      title: '检测统计',
      description: '按类型、学生和时间筛选后重新计算本地统计图表。',
      to: '/ledger-stats',
      tag: '统计',
      metric: '筛选重算',
    },
    {
      title: '质量仪表盘',
      description: '查看本学院学生论文质量指标分布和缺失项。',
      to: '/quality-dashboard',
      tag: '质量',
      metric: '缺失追踪',
    },
  ],
  SCHOOL_ADMIN: [
    {
      title: '学校规则配置',
      description: '维护全校默认规则，导入 JSON 规则草稿并发布生效。',
      to: '/rule-config',
      tag: '规则',
      metric: '全校默认',
    },
    {
      title: '本地比对样本库',
      description: '导入或删除本地查重样本，供相似度检测使用。',
      to: '/duplication-corpus',
      tag: '样本',
      metric: 'SQLite 存储',
    },
    {
      title: '检测记录台账',
      description: '查看全校范围内所有检测类型的可追溯记录。',
      to: '/ledger-records',
      tag: '台账',
      metric: '全校范围',
    },
    {
      title: '质量仪表盘',
      description: '聚合全校学生质量指标，按时间和类型筛选。',
      to: '/quality-dashboard',
      tag: '质量',
      metric: '全校汇总',
    },
  ],
};

const catalogGroups: Array<{ title: string; modules: ModuleLink[] }> = [
  {
    title: '论文检测与生成',
    modules: [
      { title: '规范性检测', description: '章节顺序、标点配对、参考文献、禁用词和长句检测。', to: '/normative-check', tag: '检测', metric: '可解释规则' },
      { title: '规范报告历史', description: '查看本人规范检测历史、原文定位和 JSON 下载。', to: '/normative-reports', tag: '历史', metric: '问题定位' },
      { title: '相似度检测', description: '本地样本库比对、相似片段和写作风险提示。', to: '/duplication-detect', tag: '检测', metric: '本地样本' },
      { title: '相似度历史', description: '查看相似度报告详情和下载结果 JSON。', to: '/duplication-history', tag: '历史', metric: '报告下载' },
      { title: '整篇润色', description: '按基础、标准、增强等级生成整篇文本润色结果。', to: '/whole-polish', tag: '润色', metric: '全文结果' },
      { title: '局部润色', description: '对粘贴片段进行局部改写，并保留差异片段。', to: '/local-polish', tag: '润色', metric: '差异追踪' },
    ],
  },
  {
    title: '评估与评阅',
    modules: [
      { title: '创新性量表评估', description: '录入五维度证据和改进计划，保存评估快照。', to: '/innovation-assessment', tag: '创新', metric: '硕博权重' },
      { title: '创新评分试算', description: '只计算五维等级得分，不保存完整评估快照。', to: '/innovation-scoring', tag: '试算', metric: '公式透明' },
      { title: '创新评估历史', description: '查看本人创新性评估记录和详细报告。', to: '/innovation-history', tag: '历史', metric: '快照追溯' },
      { title: '规则化辅助评阅', description: '基于内置模板生成客观评分和待人工确认项。', to: '/ai-review', tag: '评阅', metric: '五类模板' },
      { title: '辅助评阅历史', description: '按时间倒序查看辅助评阅记录并进入结果页。', to: '/ai-review/history', tag: '历史', metric: '结果复核' },
      { title: '润色历史', description: '查看整篇与局部润色历史记录。', to: '/polish-history', tag: '历史', metric: '改写记录' },
    ],
  },
  {
    title: '台账、质量与师生流转',
    modules: [
      { title: '检测记录台账', description: '按权限范围查询、筛选和导出所有检测记录。', to: '/ledger-records', roles: ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'], tag: '台账', metric: 'CSV 导出' },
      { title: '检测统计', description: '本地计算类型统计、学生数、今日数量和趋势。', to: '/ledger-stats', roles: ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'], tag: '统计', metric: 'SVG/CSS 图表' },
      { title: '质量仪表盘', description: '聚合四项可量化指标，不用缺失数据代替 0 分。', to: '/quality-dashboard', roles: ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'], tag: '质量', metric: '平均与分布' },
      { title: '单学生质量画像', description: '查看四类最新记录来源、雷达图和综合分完整性。', to: '/student-quality-portrait', tag: '画像', metric: '来源可追溯' },
      { title: '学生报告提交', description: '把本人已完成报告推送给导师，生成站内待办。', to: '/student-report-submissions', roles: ['STUDENT'], tag: '提交', metric: '批阅流转' },
      { title: '导师待批阅', description: '导师查看、筛选并处理分配给自己的待办。', to: '/supervisor-review-queue', roles: ['SUPERVISOR'], tag: '批阅', metric: '状态流转' },
      { title: '学生查看批阅结果', description: '查看导师反馈、历史轮次并下载 JSON 结果。', to: '/student-report-results', roles: ['STUDENT'], tag: '反馈', metric: '已查阅状态' },
    ],
  },
  {
    title: '管理配置',
    modules: [
      { title: '规则配置', description: '学校/学院规则发布、覆盖、重置和 JSON 草稿导入。', to: '/rule-config', roles: ['COLLEGE_ADMIN', 'SCHOOL_ADMIN'], tag: '管理', metric: '分级规则' },
      { title: '本地比对样本库', description: '学校管理员维护查重样本，本地原型不接真实论文库。', to: '/duplication-corpus', roles: ['SCHOOL_ADMIN'], tag: '管理', metric: '样本库' },
    ],
  },
];

function isAllowed(userRole: AuthRole | null, roles?: AuthRole[]) {
  return !roles || !userRole || roles.includes(userRole);
}

function roleList(roles?: AuthRole[]) {
  if (!roles) return '全部角色';
  return roles.map((role) => roleLabels[role]).join(' / ');
}

function ModuleEntry({ module, userRole }: { module: ModuleLink; userRole: AuthRole | null }) {
  const allowed = isAllowed(userRole, module.roles);
  const className = `group block h-full rounded-lg border p-4 transition ${
    allowed
      ? 'border-slate-200 bg-white shadow-sm hover:-translate-y-0.5 hover:border-[#2f80ed] hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#2f80ed]'
      : 'border-slate-200 bg-slate-50 opacity-60'
  }`;

  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <span className="rounded bg-[#eaf2ff] px-2.5 py-1 text-xs font-black text-[#1d5fbf]">{module.tag}</span>
        <span className="text-right text-xs font-bold text-slate-500">{module.metric}</span>
      </div>
      <h3 className="mt-4 text-lg font-black text-[#142f4c]">{module.title}</h3>
      <p className="mt-2 min-h-12 text-sm leading-6 text-slate-600">{module.description}</p>
      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-sm font-black">
        <span className={allowed ? 'text-[#2f80ed]' : 'text-slate-400'}>{allowed ? '进入模块' : '当前角色不可用'}</span>
        <span className="text-slate-400">{roleList(module.roles)}</span>
      </div>
    </>
  );

  if (!allowed && userRole) {
    return <article className={className}>{content}</article>;
  }

  return (
    <Link className={className} to={module.to}>
      {content}
    </Link>
  );
}

function HomePage() {
  const { status, user, logout } = useAuthSession();
  const userRole = user?.role || null;
  const visiblePrimaryModules = user ? primaryModules[user.role] : primaryModules.STUDENT;
  const portraitPath = user?.role === 'STUDENT' ? `/student-quality-portrait/${user.id}` : '/student-quality-portrait';

  return (
    <main className="min-h-screen bg-[#eef2f6] text-slate-900">
      <header className="border-b border-[#183a5d] bg-[#1f3f63] text-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-bold text-[#a8d4ff]">LOCAL EXPLAINABLE DEGREE REVIEW</p>
            <h1 className="mt-1 text-2xl font-black md:text-3xl">智慧学位 AI 评阅辅助系统</h1>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm font-bold">
            {status === 'loading' ? <span className="rounded border border-white/20 px-3 py-2">正在恢复会话</span> : null}
            {user ? (
              <>
                <span className="rounded border border-white/20 bg-white/10 px-3 py-2">
                  {user.username} · {roleLabels[user.role]} · {user.scope === 'SCHOOL' ? '全校范围' : '本学院范围'}
                </span>
                <button className="rounded bg-white px-4 py-2 font-black text-[#1f3f63]" type="button" onClick={() => void logout()}>
                  退出
                </button>
              </>
            ) : (
              <Link className="rounded bg-white px-4 py-2 font-black text-[#1f3f63]" to="/auth">
                登录演示账号
              </Link>
            )}
          </div>
        </div>
      </header>

      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-6 py-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="flex flex-wrap gap-2 text-xs font-black">
              <span className="rounded bg-[#d50000] px-3 py-1.5 text-white">用户层</span>
              <span className="rounded bg-[#4b79c9] px-3 py-1.5 text-white">核心功能层</span>
              <span className="rounded bg-[#334155] px-3 py-1.5 text-white">数据算法引擎层</span>
            </div>
            <h2 className="mt-5 max-w-3xl text-4xl font-black leading-tight text-[#102a43] md:text-5xl">
              从首页直接进入检测、评估、台账和师生批阅。
            </h2>
            <p className="mt-5 max-w-3xl text-base leading-8 text-slate-600">
              本系统面向学生、导师、学院管理员和学校管理员。所有核心结果由本地规则、公式和 SQLite 持久化数据产生，不依赖 jAccount、短信、微信扫码、外部大模型或校外文献库。
            </p>
          </div>
          <aside className="border-l-4 border-[#d50000] bg-[#f7f9fc] p-5">
            <h2 className="text-lg font-black text-[#1f3f63]">{user ? `${roleLabels[user.role]}工作台` : '演示入口'}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {user ? roleNotes[user.role] : '未登录时可以先查看模块入口；进入受限页面后会提示登录。默认演示密码为 ArcDemo123!。'}
            </p>
            <div className="mt-5 grid grid-cols-2 gap-2 text-sm font-bold">
              {(['STUDENT', 'SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'] as AuthRole[]).map((role) => (
                <span key={role} className={`rounded border px-3 py-2 ${user?.role === role ? 'border-[#2f80ed] bg-[#eaf2ff] text-[#1d5fbf]' : 'border-slate-200 bg-white text-slate-600'}`}>
                  {roleLabels[role]}
                </span>
              ))}
            </div>
          </aside>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-8">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-black text-[#d50000]">推荐入口</p>
            <h2 className="mt-1 text-2xl font-black text-[#102a43]">{user ? '按当前角色优先展示' : '学生常用流程'}</h2>
          </div>
          <Link className="inline-flex rounded bg-[#2f80ed] px-5 py-3 text-sm font-black text-white" to={user ? portraitPath : '/auth'}>
            {user ? '查看质量画像' : '先登录'}
          </Link>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visiblePrimaryModules.map((module) => (
            <ModuleEntry key={module.to} module={module} userRole={userRole} />
          ))}
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-6 py-8">
          <h2 className="text-2xl font-black text-[#102a43]">全功能模块入口</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">按需求模块归类展示。已登录时，当前角色不可使用的入口会显示为灰色。</p>
          <div className="mt-6 space-y-8">
            {catalogGroups.map((group) => (
              <section key={group.title} aria-labelledby={`home-group-${group.title}`}>
                <h3 id={`home-group-${group.title}`} className="border-l-4 border-[#2f80ed] pl-3 text-lg font-black text-[#1f3f63]">
                  {group.title}
                </h3>
                <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {group.modules.map((module) => (
                    <ModuleEntry key={`${group.title}-${module.to}-${module.title}`} module={module} userRole={userRole} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-4 px-6 py-8 md:grid-cols-3">
        {[
          ['本地认证', '四个演示账号由后端启动时幂等写入，密码使用 bcrypt 哈希保存。'],
          ['本地算法', '相似度、创新量表、评阅评分均由可解释规则和公式生成。'],
          ['本地流转', '报告提交、导师待办和反馈结果都保存在 SQLite 中，不发送外部消息。'],
        ].map(([title, text]) => (
          <article key={title} className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-black text-[#102a43]">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

export default HomePage;
