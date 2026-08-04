import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import RuleDraftImportPanel from '../components/RuleDraftImportPanel';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  fetchRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
  type RuleConfigDto,
} from '../api/ruleConfig';

function RuleConfigPage() {
  const { status, user } = useAuthSession();
  const [rules, setRules] = useState<RuleConfigDto[]>([]);
  const [loadingRules, setLoadingRules] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canManageRules = user?.role === 'SCHOOL_ADMIN' || user?.role === 'COLLEGE_ADMIN';
  const roleLabel = useMemo(() => (user ? `${user.username}（${user.role}）` : '未登录'), [user]);

  useEffect(() => {
    if (!canManageRules) {
      setRules([]);
      return;
    }

    setLoadingRules(true);
    setErrorMessage(null);
    fetchRuleConfigurations(user?.role === 'COLLEGE_ADMIN' ? { level: 'college', college_id: user.collegeId } : { level: 'school' })
      .then((response) => setRules(response.rules))
      .catch((error) => setErrorMessage(error instanceof Error ? error.message : '规则配置加载失败'))
      .finally(() => setLoadingRules(false));
  }, [canManageRules, user]);

  if (status === 'loading') {
    return <main className="px-6 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">规范性检测规则配置</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录学校或学院管理员账号后维护规则。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  if (!canManageRules) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-red-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">无权维护规则配置</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">仅学校管理人员和学院管理人员可以访问此页面。</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white px-6 py-8 text-slate-900">
      <section className="mx-auto max-w-7xl overflow-hidden rounded-2xl border border-[#D8DDE6] shadow-sm">
        <header className="flex items-center justify-between bg-[#213B63] px-6 py-4 text-white">
          <h1 className="text-2xl font-black">规范性检测规则配置</h1>
          <span className="rounded-full bg-[#3D8BFF] px-4 py-2 text-sm font-bold">{roleLabel}</span>
        </header>

        <section className="border-t border-[#D8DDE6]">
          <div className="bg-[#243E66] px-5 py-3 text-lg font-bold text-white">可视化显性规则配置</div>
          <div className="p-5">
            {loadingRules ? <p className="text-sm font-semibold text-slate-500">正在加载规则配置…</p> : null}
            {errorMessage ? <p className="text-sm font-semibold text-red-600">{errorMessage}</p> : null}
            {!loadingRules && !errorMessage && rules.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[#D8DDE6] p-6 text-center text-sm text-slate-500">
                暂无运行时规则配置。学校默认值和学院覆盖将在后端接口返回后显示。
              </p>
            ) : null}
            {rules.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[#213B63] text-white">
                    <tr>
                      <th className="px-3 py-3">rule_id</th>
                      <th className="px-3 py-3">规则标题</th>
                      <th className="px-3 py-3">类别</th>
                      <th className="px-3 py-3">严重程度</th>
                      <th className="px-3 py-3">启用状态</th>
                      <th className="px-3 py-3">匹配参数</th>
                      <th className="px-3 py-3">提示文案</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <tr key={`${rule.source}-${rule.college_id || 'school'}-${rule.rule_id}`} className="border-b border-[#D8DDE6]">
                        <td className="px-3 py-3 font-mono text-xs">{rule.rule_id}</td>
                        <td className="px-3 py-3 font-semibold">{rule.title}</td>
                        <td className="px-3 py-3">{rule.category}</td>
                        <td className="px-3 py-3">{rule.severity}</td>
                        <td className="px-3 py-3">{rule.enabled ? '启用' : '停用'}</td>
                        <td className="px-3 py-3 font-mono text-xs">{JSON.stringify(rule.match_params)}</td>
                        <td className="px-3 py-3">{rule.prompt}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </section>

        <RuleDraftImportPanel />

        <footer className="flex flex-wrap gap-3 border-t border-[#D8DDE6] bg-slate-50 p-5">
          <button className="rounded-lg bg-[#3D8BFF] px-5 py-2 text-sm font-bold text-white" type="button" onClick={() => void publishRuleConfiguration}>
            提交生效
          </button>
          <button className="rounded-lg bg-[#54C83A] px-5 py-2 text-sm font-bold text-white" type="button" onClick={() => void resetCollegeRuleConfiguration}>
            学院重置继承学校值
          </button>
        </footer>
      </section>
    </main>
  );
}

export default RuleConfigPage;
