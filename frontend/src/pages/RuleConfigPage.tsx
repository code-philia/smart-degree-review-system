import { useEffect, useMemo, useState } from 'react';
import RuleDraftImportPanel from '../components/RuleDraftImportPanel';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  fetchRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
  type RuleConfigDto,
} from '../api/ruleConfig';
import {
  Button,
  Card,
  DataTable,
  DataTableCell,
  DataTableHead,
  DataTableRow,
  EmptyState,
  ErrorState,
  LinkButton,
  LoadingState,
  PageHeader,
} from '../components/ui';

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
    fetchRuleConfigurations(
      user?.role === 'COLLEGE_ADMIN' ? { level: 'college', college_id: user.collegeId } : { level: 'school' },
    )
      .then((response) => setRules(response.rules))
      .catch((error) => setErrorMessage(error instanceof Error ? error.message : '规则配置加载失败'))
      .finally(() => setLoadingRules(false));
  }, [canManageRules, user]);

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">规范性检测规则配置</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录学校或学院管理员账号后维护规则。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  if (!canManageRules) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">无权维护规则配置</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">仅学校管理人员和学院管理人员可以访问此页面。</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="text-slate-900">
      <PageHeader
        title="规范性检测规则配置"
        actions={<span className="rounded-full bg-[#3D8BFF] px-4 py-2 text-sm font-bold text-white">{roleLabel}</span>}
      />
      <section className="mx-auto max-w-7xl overflow-hidden rounded-2xl border border-[#D8DDE6] shadow-sm">
        <section>
          <div className="bg-[#243E66] px-5 py-3 text-lg font-bold text-white">可视化显性规则配置</div>
          <div className="p-5">
            {loadingRules ? <LoadingState label="正在加载规则配置…" /> : null}
            {errorMessage ? <ErrorState message={errorMessage} /> : null}
            {!loadingRules && !errorMessage && rules.length === 0 ? (
              <EmptyState title="暂无运行时规则配置" description="学校默认值和学院覆盖将在后端接口返回后显示。" />
            ) : null}
            {rules.length > 0 ? (
              <DataTable aria-label="可视化显性规则配置">
                <thead>
                  <DataTableRow className="hover:bg-transparent">
                    <DataTableHead>rule_id</DataTableHead>
                    <DataTableHead>规则标题</DataTableHead>
                    <DataTableHead>类别</DataTableHead>
                    <DataTableHead>严重程度</DataTableHead>
                    <DataTableHead>启用状态</DataTableHead>
                    <DataTableHead>匹配参数</DataTableHead>
                    <DataTableHead>提示文案</DataTableHead>
                  </DataTableRow>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <DataTableRow key={`${rule.source}-${rule.college_id || 'school'}-${rule.rule_id}`}>
                      <DataTableCell className="font-mono text-xs text-slate-500">{rule.rule_id}</DataTableCell>
                      <DataTableCell className="font-semibold text-slate-900">{rule.title}</DataTableCell>
                      <DataTableCell>{rule.category}</DataTableCell>
                      <DataTableCell>{rule.severity}</DataTableCell>
                      <DataTableCell>{rule.enabled ? '启用' : '停用'}</DataTableCell>
                      <DataTableCell className="font-mono text-xs text-slate-500">
                        {JSON.stringify(rule.match_params)}
                      </DataTableCell>
                      <DataTableCell>{rule.prompt}</DataTableCell>
                    </DataTableRow>
                  ))}
                </tbody>
              </DataTable>
            ) : null}
          </div>
        </section>

        <RuleDraftImportPanel />

        <footer className="flex flex-wrap gap-3 border-t border-[#D8DDE6] bg-slate-50 p-5">
          <Button onClick={() => void publishRuleConfiguration}>提交生效</Button>
          <Button variant="secondary" onClick={() => void resetCollegeRuleConfiguration}>
            学院重置继承学校值
          </Button>
        </footer>
      </section>
    </div>
  );
}

export default RuleConfigPage;
