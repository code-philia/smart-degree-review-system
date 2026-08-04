import { useAuthSession } from './AuthSessionProvider';

const roleMenuLabels = {
  STUDENT: '学生菜单',
  SUPERVISOR: '导师菜单',
  SCHOOL_ADMIN: '学校管理菜单',
  COLLEGE_ADMIN: '学院管理菜单',
} as const;

function RoleAwareHomeMenu() {
  const { status, user } = useAuthSession();

  if (status === 'loading') {
    return <p className="text-sm font-semibold text-slate-500">正在加载登录状态…</p>;
  }

  if (!user) {
    return <p className="text-sm font-semibold text-slate-500">请登录后查看角色菜单和数据范围。</p>;
  }

  return (
    <section className="rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4 text-slate-800" aria-label="当前角色菜单">
      <h2 className="text-lg font-black text-blue-900">{roleMenuLabels[user.role]}</h2>
      <p className="mt-2 text-sm font-semibold text-blue-700">数据范围：{user.scope === 'SCHOOL' ? '全校' : '本学院'}</p>
    </section>
  );
}

export default RoleAwareHomeMenu;
