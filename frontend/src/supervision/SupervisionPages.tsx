import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowUpRight, ChevronLeft, ChevronRight, Files, MessageSquareText, Search, ShieldCheck, X } from 'lucide-react';
import { Link, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from '../components/shadcn/dialog';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../components/paperLint/model';
import { formatChinaDateTime } from '../utils/dateTime';
import { fetchSupervisionFeedback, fetchSupervisionReport, fetchSupervisionReports, fetchSupervisionRules, type SupervisionFeedback, type SupervisionReportDetail, type SupervisionPage, type SupervisionReport } from '../api/supervision';
import type { PaperLintRule } from '../api/paperLint';
import type { SupervisionOutlet } from './SupervisionShell';

function useSearchQuery() {
  const [draft, setDraft] = useState(''), [query, setQuery] = useState('');
  useEffect(() => { const timer = window.setTimeout(() => setQuery(draft.trim()), 300); return () => window.clearTimeout(timer); }, [draft]);
  return { draft, setDraft, query };
}
function time(value: string) { return formatChinaDateTime(value, { includeSeconds: false }); }
function Pagination({ page, total, pageSize, onPage }: { page: number; total: number; pageSize: number; onPage: (page: number) => void }) {
  const last = Math.max(1, Math.ceil(total / pageSize));
  return <div className="sup-pagination"><p>共 <strong>{total}</strong> 条记录<span>每页 {pageSize} 条</span></p><div><button aria-label="上一页" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={17} /></button><span>第 <strong>{page}</strong> / {last} 页</span><button aria-label="下一页" disabled={page >= last} onClick={() => onPage(page + 1)}><ChevronRight size={17} /></button></div></div>;
}
function StateRow({ columns, loading, error, empty }: { columns: number; loading: boolean; error: boolean; empty: boolean }) {
  if (!loading && !error && !empty) return null;
  return <tr><td colSpan={columns}><div className={`sup-table-state ${error ? 'error' : ''}`} role="status">{loading ? <><span className="sup-loading-dot" />正在读取数据…</> : error ? '数据暂时无法加载，请点击上方刷新数据重试' : <><Search size={26} strokeWidth={1.4} />暂无匹配记录<span>试试调整搜索内容或筛选条件</span></>}</div></td></tr>;
}
function Owner({ username, name }: { username: string; name?: string | null }) {
  return <div className="sup-owner"><span className="sup-owner-avatar">{Array.from(name || username)[0]}</span><div><strong>{name || username}</strong>{name && name !== username ? <span>{username}</span> : null}</div></div>;
}
function reportLink(report: SupervisionReport) { return `/admin/reports/${encodeURIComponent(report.id)}` + (report.report_type && report.report_type !== 'paper_lint' ? `?type=${report.report_type}` : ''); }

export function SupervisionReportsPage() {
  const { refreshKey } = useOutletContext<SupervisionOutlet>();
  const search = useSearchQuery(); const [page, setPage] = useState(1), [type, setType] = useState('all'), [field, setField] = useState('filename');
  const [data, setData] = useState<SupervisionPage<SupervisionReport> | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState(false);
  useEffect(() => { setPage(1); }, [search.query, type, field]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(false);
    fetchSupervisionReports({ page, q: search.query, type, search_field: field }, controller.signal).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(() => { if (!controller.signal.aborted) setError(true); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, search.query, type, field, refreshKey]);
  return <section className="sup-panel"><div className="sup-panel-heading"><div><h1>全部报告</h1><p>查看各用户已保存的检测结果与论文原文</p></div><span className="sup-total-badge">{data?.total ?? '—'} 份报告</span></div>
    <div className="sup-toolbar"><div className="sup-search"><select aria-label="报告搜索类别" value={field} onChange={event => setField(event.target.value)}><option value="filename">论文名称</option><option value="display_name">用户姓名</option><option value="username">用户账号</option><option value="report_id">报告编号</option></select><Search size={17} /><input type="search" aria-label="搜索报告" placeholder="输入搜索内容" value={search.draft} maxLength={200} onChange={event => search.setDraft(event.target.value)} /></div><select aria-label="报告类型" value={type} onChange={event => setType(event.target.value)}><option value="all">全部报告类型</option><option value="paper_lint">论文规范检测</option><option value="normative">早期规范检测</option><option value="duplication">查重检测</option><option value="example">示例规则检测</option></select><span className="sup-toolbar-note"><ShieldCheck size={14} />查看全部用户记录</span></div>
    <div className="sup-table-scroll"><table className="sup-table" aria-label="全部用户检测报告" aria-busy={loading}><thead><tr><th>论文 / 报告</th><th>所属用户</th><th>检测结果</th><th>检测时间</th><th><span className="sup-sr-only">操作</span></th></tr></thead><tbody>
      <StateRow columns={5} loading={loading} error={error} empty={!data?.items.length} />
      {!loading && !error ? data?.items.map(report => <tr key={`${report.report_type}:${report.id}`}><td><Link className="sup-document" to={reportLink(report)}><span className="sup-document-icon"><Files size={19} /></span><span>{report.source_filename}<small className="sup-report-kind">{report.type_label || '论文规范检测'}</small></span></Link></td><td><Owner username={report.owner.username} name={report.owner.display_name} /></td><td>{report.summary ? report.summary.finding_count ? <div className="sup-findings-count"><strong>{report.summary.finding_count} 项问题</strong><span>{report.summary.error_finding_count ? <i className="sup-level error">严重 {report.summary.error_finding_count}</i> : null}{report.summary.warning_finding_count ? <i className="sup-level warning">警告 {report.summary.warning_finding_count}</i> : null}{report.summary.info_finding_count ? <i className="sup-level info">提示 {report.summary.info_finding_count}</i> : null}</span></div> : <span className="sup-pill positive">无告警记录</span> : <span className="sup-pill neutral">{report.report_type && report.report_type !== 'paper_lint' ? '查看已保存结果' : '报告数据待核查'}</span>}</td><td><time className="sup-date">{time(report.created_at)}</time></td><td><Link className="sup-row-action" to={reportLink(report)}>查看报告<ArrowUpRight size={15} /></Link></td></tr>) : null}
    </tbody></table></div><Pagination page={page} total={data?.total ?? 0} pageSize={data?.page_size ?? 20} onPage={setPage} />
  </section>;
}

export function SupervisionFeedbackPage() {
  const { refreshKey } = useOutletContext<SupervisionOutlet>();
  const search = useSearchQuery(); const [page, setPage] = useState(1), [type, setType] = useState('all'), [value, setValue] = useState('all'), [field, setField] = useState('content');
  const [data, setData] = useState<SupervisionPage<SupervisionFeedback> | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState(false);
  const [selected, setSelected] = useState<SupervisionFeedback | null>(null);
  useEffect(() => { setPage(1); }, [search.query, type, value, field]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(false);
    fetchSupervisionFeedback({ page, q: search.query, type, value, search_field: field }, controller.signal).then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(() => { if (!controller.signal.aborted) setError(true); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, search.query, type, value, field, refreshKey]);
  return <><section className="sup-panel"><div className="sup-panel-heading"><div><h1>全部反馈</h1><p>使用反馈、检测评价与修复建议评价，统一查看</p></div><span className="sup-total-badge">{data?.total ?? '—'} 条反馈</span></div>
    <div className="sup-toolbar"><div className="sup-search"><select aria-label="反馈搜索类别" value={field} onChange={event => setField(event.target.value)}><option value="content">反馈内容</option><option value="filename">论文名称</option><option value="display_name">用户姓名</option><option value="username">用户账号</option><option value="rule_id">规则编号</option></select><Search size={17} /><input type="search" aria-label="搜索反馈" placeholder="输入搜索内容" value={search.draft} maxLength={200} onChange={event => search.setDraft(event.target.value)} /></div><select aria-label="反馈类型" value={type} onChange={event => setType(event.target.value)}><option value="all">全部类型</option><option value="system">使用反馈</option><option value="finding">检测结果评价</option><option value="suggestion">修复建议评价</option></select><select aria-label="反馈评价" value={value} onChange={event => setValue(event.target.value)}><option value="all">全部评价</option><option value="negative">点踩 / 不满意</option><option value="positive">点赞 / 满意</option></select></div>
    <div className="sup-table-scroll"><table className="sup-table sup-feedback-table" aria-label="全部用户反馈" aria-busy={loading}><thead><tr><th>反馈内容</th><th>反馈用户</th><th>关联论文 / 规则</th><th>评价</th><th>反馈时间</th><th><span className="sup-sr-only">操作</span></th></tr></thead><tbody>
      <StateRow columns={6} loading={loading} error={error} empty={!data?.items.length} />
      {!loading && !error ? data?.items.map(item => <tr key={`${item.type}:${item.id}`}><td><div className="sup-feedback-preview"><span className={`sup-type-label ${item.type}`}>{item.type_label}</span><p>{item.comment || item.reason_text || item.reason_label || (item.feedback_value === 'positive' ? '用户认可此项结果' : '用户未填写补充说明')}</p></div></td><td><Owner username={item.username} name={item.display_name} /></td><td><div className="sup-feedback-source">{item.report_id ? <Link to={`/admin/reports/${encodeURIComponent(item.report_id)}`}>{item.source_filename || '查看关联报告'}</Link> : <span>系统使用反馈</span>}{item.rule_title ? <small>{item.rule_title}</small> : null}</div></td><td><span className={`sup-pill ${item.feedback_value === 'negative' || (item.satisfaction_score !== null && item.satisfaction_score <= 2) ? 'negative' : item.feedback_value === 'positive' || (item.satisfaction_score ?? 0) >= 4 ? 'positive' : 'neutral'}`}>{item.feedback_label}</span></td><td><time className="sup-date">{time(item.created_at)}</time></td><td><button className="sup-row-action" aria-label="查看反馈详情" onClick={() => setSelected(item)}>详情<ChevronRight size={15} /></button></td></tr>) : null}
    </tbody></table></div><Pagination page={page} total={data?.total ?? 0} pageSize={data?.page_size ?? 20} onPage={setPage} />
  </section><Dialog open={Boolean(selected)} onOpenChange={open => { if (!open) setSelected(null); }}><DialogContent className="sup-feedback-dialog" aria-describedby="sup-feedback-description" showCloseButton={false}><DialogClose asChild><button className="sup-dialog-close" aria-label="关闭反馈详情"><X size={18} /></button></DialogClose>{selected ? <><div className="sup-dialog-heading"><span className="sup-dialog-icon"><MessageSquareText size={22} /></span><div><DialogTitle>反馈详情</DialogTitle><DialogDescription id="sup-feedback-description">{selected.type_label} · {time(selected.created_at)}</DialogDescription></div></div><div className="sup-dialog-body"><div className="sup-detail-person"><Owner username={selected.username} name={selected.display_name} /><span className="sup-pill neutral">{selected.feedback_label}</span></div>
      {selected.type === 'system' ? <><div className="sup-detail-section"><h3>使用反馈说明</h3><p>{selected.comment || '未填写补充说明'}</p></div>{selected.improvement_labels.length ? <div className="sup-detail-section"><h3>希望改进的方面</h3><div className="sup-detail-tags">{selected.improvement_labels.map(label => <span key={label}>{label}</span>)}</div></div> : null}</> : <><div className="sup-detail-section"><h3>反馈原因</h3><p>{selected.reason_label || '未选择原因'}</p>{selected.reason_text ? <p className="sup-detail-comment">{selected.reason_text}</p> : null}</div><div className="sup-detail-section"><h3>对应检测内容</h3><p className="sup-detail-rule">{selected.rule_title || selected.rule_id}</p><p>{selected.finding_text || '此条反馈没有可展示的检测描述，请查看关联报告。'}</p></div>{selected.saved_suggestion ? <div className="sup-detail-section"><h3>已保存的修复建议 <span>第 {selected.saved_suggestion.generation} 版</span></h3>{selected.saved_suggestion.actions.length ? selected.saved_suggestion.actions.map((action, index) => <p className="sup-saved-action" key={index}>{action.instruction || action.replacement || '此条建议没有文字说明'}</p>) : <p>此版本未保存具体修改动作。</p>}</div> : selected.type === 'suggestion' ? <div className="sup-detail-section"><h3>修复建议版本</h3><p>第 {selected.generation ?? '—'} 版，具体建议暂不可读取。</p></div> : null}</>}
      {selected.report_id ? <div className="sup-detail-report"><div><small>关联论文</small><p>{selected.source_filename || selected.report_id}</p></div><Link className="sup-button sup-primary" to={`/admin/reports/${encodeURIComponent(selected.report_id)}`} onClick={() => setSelected(null)}>查看关联报告<ArrowUpRight size={15} /></Link></div> : null}
    </div></> : null}</DialogContent></Dialog></>;
}

export function SupervisionReportPage() {
  const { reportId = '' } = useParams(); const { refreshKey } = useOutletContext<SupervisionOutlet>();
  const [params] = useSearchParams(), type = params.get('type') || 'paper_lint';
  const [data, setData] = useState<SupervisionReportDetail | null>(null), [rules, setRules] = useState<PaperLintRule[]>([]), [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError(false);
    Promise.all([fetchSupervisionReport(reportId, controller.signal, type), type === 'paper_lint' ? fetchSupervisionRules(controller.signal) : Promise.resolve([])]).then(([report, catalog]) => { if (!controller.signal.aborted) { setData(report); setRules(catalog); } })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [reportId, type, refreshKey]);
  if (error) return <section className="sup-panel sup-report-state"><h1>报告暂不可读取</h1><p>请确认报告仍然存在，或刷新重试。</p><Link to="/admin/reports" className="sup-button">返回全部报告</Link></section>;
  if (!data) return <section className="sup-panel sup-report-state" role="status">正在加载报告与论文原文…</section>;
  if (data.legacy) return <LegacyReport data={data} />;
  const { report, owner } = data, pdf = `/api/supervision/reports/${encodeURIComponent(reportId)}/pdf`;
  const findings = flattenPaperLintFindings(report.result);
  return <section className="sup-report-detail"><Link className="sup-back-link" to="/admin/reports"><ArrowLeft size={16} />返回全部报告</Link><div className="sup-panel sup-report-heading"><div><span className="sup-eyebrow">报告详情</span><h1>{report.source_filename}</h1><div className="sup-report-meta"><Owner username={owner.username} name={owner.display_name} /><time>{time(report.created_at)}</time></div></div><span className="sup-scope"><ShieldCheck size={15} />只读查看</span></div><div className="sup-report-workspace"><PaperLintWorkspace key={report.id} file={{ name: report.source_filename, url: pdf }} openPdfUrl={pdf} findings={findings} rules={rules} selectedRuleIds={report.selected_rule_ids} ruleRuns={report.result.rule_runs} numericReviewRun={report.result.rule_runs.find(run => run.rule_id === 'abstract_numeric_consistency_check')} readOnly /></div></section>;
}


const savedFieldLabels: Record<string, string> = { issues: '检测问题', severity_counts: '问题统计', severity: '级别', message: '问题说明', suggestion: '修改建议', title: '标题', rule_title: '规则', line: '行号', location: '位置', original_text: '原文', text: '文本', reason: '原因', description: '说明', summary: '检测摘要', findings: '检测结果', total_similarity_rate: '总相似度', top_matches: '相似来源', matched_paragraphs: '匹配段落', risk: '风险分析', score: '分数', level: '等级', error: '严重', warning: '警告', info: '提示', detection_type_label: '检测类型', sample_title: '来源标题', similarity_rate: '相似度' };
function SavedResult({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) return <span className="sup-empty-value">未保存</span>;
  if (typeof value !== 'object') return <span>{String(value)}</span>;
  if (depth > 6) return <pre>{JSON.stringify(value, null, 2)}</pre>;
  if (Array.isArray(value)) return value.length ? <div className="sup-saved-list">{value.map((item, index) => <div key={index}><SavedResult value={item} depth={depth + 1} /></div>)}</div> : <span className="sup-empty-value">无记录</span>;
  return <dl className="sup-saved-fields">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{savedFieldLabels[key] || key}</dt><dd><SavedResult value={item} depth={depth + 1} /></dd></div>)}</dl>;
}
function LegacyReport({ data }: { data: SupervisionReportDetail }) {
  if (!data.legacy) return null;
  const { legacy, owner } = data;
  return <section className="sup-report-detail"><Link className="sup-back-link" to="/admin/reports"><ArrowLeft size={16} />返回全部报告</Link><div className="sup-panel sup-report-heading"><div><span className="sup-eyebrow">{legacy.type_label}</span><h1>{legacy.source_filename}</h1><div className="sup-report-meta"><Owner username={owner.username} name={owner.display_name} /><time>{time(legacy.created_at)}</time></div></div><span className="sup-scope"><ShieldCheck size={15} />只读查看</span></div><div className="sup-legacy-grid">{legacy.original_text ? <section className="sup-panel sup-legacy-section"><h2>检测原文</h2><p className="sup-saved-original">{legacy.original_text}</p></section> : null}<section className="sup-panel sup-legacy-section"><h2>已保存的检测结果</h2><SavedResult value={legacy.saved_result} />{legacy.has_pdf ? <a className="sup-button" href={`/api/supervision/reports/${encodeURIComponent(legacy.id)}/pdf?type=example`} target="_blank" rel="noopener noreferrer">查看原始 PDF<ArrowUpRight size={15} /></a> : null}</section></div></section>;
}
