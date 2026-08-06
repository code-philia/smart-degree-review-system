import type { AuthRole } from '../api/authSession';

export type NavItem = {
  label: string;
  to: string;
  roles?: AuthRole[];
  matchPrefix?: string;
};

export type NavGroup = {
  key: string;
  title: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'detection',
    title: '检测与生成',
    items: [
      { label: '规范性检测', to: '/normative-check' },
      { label: '规范报告历史', to: '/normative-reports' },
      { label: '论文相似度检测', to: '/duplication-detect' },
      { label: '相似度检测历史', to: '/duplication-history' },
      { label: '整篇润色', to: '/whole-polish' },
      { label: '局部润色', to: '/local-polish' },
      { label: '润色历史', to: '/polish-history' },
    ],
  },
  {
    key: 'assessment',
    title: '评估与评阅',
    items: [
      { label: '创新性量表评估', to: '/innovation-assessment' },
      { label: '创新评分试算', to: '/innovation-scoring' },
      { label: '创新评估历史', to: '/innovation-history', matchPrefix: '/innovation-assessments' },
      { label: '规则化辅助评阅', to: '/ai-review' },
      { label: '辅助评阅历史', to: '/ai-review/history' },
    ],
  },
  {
    key: 'quality',
    title: '台账与质量',
    items: [
      { label: '检测记录台账', to: '/ledger-records', roles: ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'] },
      { label: '检测统计', to: '/ledger-stats', roles: ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'] },
      { label: '群体质量仪表盘', to: '/quality-dashboard', roles: ['SUPERVISOR', 'COLLEGE_ADMIN', 'SCHOOL_ADMIN'] },
      { label: '单学生质量画像', to: '/student-quality-portrait' },
    ],
  },
  {
    key: 'workflow',
    title: '师生流转',
    items: [
      { label: '提交报告给导师', to: '/student-report-submissions', roles: ['STUDENT'] },
      { label: '查看批阅结果', to: '/student-report-results', roles: ['STUDENT'] },
      { label: '导师待批阅', to: '/supervisor-review-queue', roles: ['SUPERVISOR'] },
    ],
  },
  {
    key: 'admin',
    title: '管理配置',
    items: [
      { label: '规则配置', to: '/rule-config', roles: ['COLLEGE_ADMIN', 'SCHOOL_ADMIN'] },
      { label: '比对样本库', to: '/duplication-corpus', roles: ['SCHOOL_ADMIN'] },
    ],
  },
  {
    key: 'system',
    title: '系统',
    items: [{ label: '系统说明', to: '/about' }],
  },
];

export function isNavItemVisible(item: NavItem, role: AuthRole | null) {
  if (!item.roles) {
    return true;
  }
  if (!role) {
    return false;
  }
  return item.roles.includes(role);
}

export function getVisibleNavGroups(role: AuthRole | null): NavGroup[] {
  if (!role) {
    return NAV_GROUPS.filter((group) => group.key === 'system');
  }
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => isNavItemVisible(item, role)),
  })).filter((group) => group.items.length > 0);
}

export function findNavItemLabel(pathname: string): { groupTitle: string; label: string } | null {
  const allItems = NAV_GROUPS.flatMap((group) => group.items.map((item) => ({ group, item })));

  const exact = allItems.find(({ item }) => item.to === pathname);
  if (exact) {
    return { groupTitle: exact.group.title, label: exact.item.label };
  }

  const prefixMatches = allItems
    .map(({ group, item }) => ({ group, item, prefix: item.matchPrefix || item.to }))
    .filter(({ prefix }) => pathname.startsWith(`${prefix}/`))
    .sort((a, b) => b.prefix.length - a.prefix.length);

  const best = prefixMatches[0];
  return best ? { groupTitle: best.group.title, label: best.item.label } : null;
}

export const roleLabels: Record<AuthRole, string> = {
  STUDENT: '学生',
  SUPERVISOR: '导师',
  COLLEGE_ADMIN: '学院管理人员',
  SCHOOL_ADMIN: '学校管理人员',
};

export const roleScopeLabels: Record<AuthRole, string> = {
  STUDENT: '本人范围',
  SUPERVISOR: '所指导学生范围',
  COLLEGE_ADMIN: '本学院范围',
  SCHOOL_ADMIN: '全校范围',
};
