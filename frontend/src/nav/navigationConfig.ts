import type { AuthRole } from '../api/authSession';

export type NavItem = {
  label: string;
  to: string;
  roles?: AuthRole[];
  matchPrefix?: string;
  relatedPrefixes?: string[];
};

export type NavGroup = {
  key: string;
  title: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'detection',
    title: '论文规范性检测',
    items: [
      { label: '论文上传', to: '/thirty-rules-check' },
      { label: '历史报告', to: '/thirty-rules-check/reports' },
    ],
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

export function findActiveNavItem(pathname: string): { group: NavGroup; item: NavItem } | null {
  const allItems = NAV_GROUPS.flatMap((group) => group.items.map((item) => ({ group, item })));

  const exact = allItems.find(({ item }) => item.to === pathname);
  if (exact) {
    return exact;
  }

  const prefixMatches = allItems
    .flatMap(({ group, item }) =>
      [item.matchPrefix || item.to, ...(item.relatedPrefixes || [])].map((prefix) => ({ group, item, prefix })),
    )
    .filter(({ prefix }) => pathname === prefix || pathname.startsWith(`${prefix}/`))
    .sort((a, b) => b.prefix.length - a.prefix.length);

  const best = prefixMatches[0];
  return best ? { group: best.group, item: best.item } : null;
}

export function findNavItemLabel(pathname: string): { groupTitle: string; label: string } | null {
  const active = findActiveNavItem(pathname);
  return active ? { groupTitle: active.group.title, label: active.item.label } : null;
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
