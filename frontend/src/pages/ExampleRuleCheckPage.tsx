import { FilePlus2, FlaskConical, Lightbulb, LockKeyhole, Pencil, Sparkles, Trash2, Upload } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui';
import {
  createExampleRule,
  exampleDocumentPdf,
  generateExampleRule,
  listExampleDocuments,
  trialExampleRule,
  updateExampleAnnotations,
  uploadExampleDocument,
  type ExampleAnnotation,
  type ExampleDocument,
  type RuleDefinition,
} from '../api/exampleRuleCheck';
import { PdfPane } from '../components/paperLint/PdfPane';

const emptyRule: RuleDefinition = {
  title: '',
  check_description: '',
  criteria: [],
  exception_notes: [],
  suggestion_template: '',
};
const labels: Record<ExampleAnnotation['type'], string> = {
  focus: '关注内容',
  pass: '合格示例',
  fail: '不合格示例',
  exception: '例外情况',
  note: '补充说明',
};
const blockLabels: Record<NonNullable<ExampleAnnotation['block_type']>, string> = {
  text: '文本',
  figure: '图表',
  table: '表格',
  equation: '公式',
};
const annotationTones: Record<ExampleAnnotation['type'], 'error' | 'warning' | 'info'> = {
  focus: 'info',
  pass: 'info',
  fail: 'error',
  exception: 'warning',
  note: 'warning',
};
type PdfBoundingRect = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  width: number;
  height: number;
  page_number: number;
};
function isPdfBoundingRect(value: unknown): value is PdfBoundingRect {
  if (!value || typeof value !== 'object') return false;
  const rect = value as Record<string, unknown>;
  return ['x1', 'y1', 'x2', 'y2', 'width', 'height', 'page_number'].every(
    (key) => typeof rect[key] === 'number' && Number.isFinite(rect[key]),
  );
}

export default function ExampleRuleCheckPage() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<ExampleDocument[] | null>(null);
  const [activeId, setActiveId] = useState('');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [intent, setIntent] = useState('');
  const [rule, setRule] = useState<RuleDefinition>(emptyRule);
  const [ruleName, setRuleName] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingAnnotationIndex, setEditingAnnotationIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<ExampleAnnotation>({
    type: 'focus',
    block_type: 'text',
    page_number: 1,
    text_excerpt: '',
    note: '',
  });
  useEffect(() => {
    listExampleDocuments()
      .then(setDocuments)
      .catch((e) => setError(e.message));
  }, []);
  const active = documents?.find((item) => item.id === activeId) || documents?.[0] || null;
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    exampleDocumentPdf(active.id)
      .then((blob) => !cancelled && setPdfFile(new File([blob], active.source_filename, { type: 'application/pdf' })))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [active?.id]);
  const annotatedIds = useMemo(
    () => documents?.filter((item) => item.annotations.length > 0).map((item) => item.id) || [],
    [documents],
  );
  const supplementalAnnotations = useMemo(
    () =>
      (active?.annotations || []).flatMap((annotation, index) =>
        isPdfBoundingRect(annotation.bounding_rect)
          ? [
              {
                id: String(index),
                pageNumber: annotation.page_number,
                boundingRect: annotation.bounding_rect,
                label: labels[annotation.type],
                tone: annotationTones[annotation.type],
              },
            ]
          : [],
      ),
    [active],
  );
  async function upload(file?: File) {
    if (!file) return;
    setBusy('upload');
    try {
      const item = await uploadExampleDocument(file);
      setDocuments((items) => [item, ...(items || [])]);
      setActiveId(item.id);
      setNotice('示例已添加。请在原文中找到能说明规则的证据，再完成标注。');
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传失败');
    } finally {
      setBusy(null);
    }
  }
  async function annotate() {
    if (!active) return setError('请先选择一份示例 PDF');
    setBusy('annotation');
    try {
      const annotations =
        editingAnnotationIndex === null
          ? [...active.annotations, draft]
          : active.annotations.map((annotation, index) => (index === editingAnnotationIndex ? draft : annotation));
      const item = await updateExampleAnnotations(active.id, annotations);
      setDocuments((items) => items?.map((x) => (x.id === item.id ? item : x)) || []);
      setDraft({ type: 'focus', block_type: 'text', page_number: draft.page_number, text_excerpt: '', note: '' });
      setEditingAnnotationIndex(null);
      setNotice(editingAnnotationIndex === null ? '证据已记录到当前示例。' : '证据已更新。');
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存标注失败');
    } finally {
      setBusy(null);
    }
  }
  async function removeAnnotation(index: number) {
    if (!active) return;
    setBusy('annotation');
    try {
      const item = await updateExampleAnnotations(
        active.id,
        active.annotations.filter((_, itemIndex) => itemIndex !== index),
      );
      setDocuments((items) => items?.map((x) => (x.id === item.id ? item : x)) || []);
      if (editingAnnotationIndex === index) {
        setEditingAnnotationIndex(null);
        setDraft({ type: 'focus', block_type: 'text', page_number: 1, text_excerpt: '', note: '' });
      }
      setNotice('证据已删除。');
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除证据失败');
    } finally {
      setBusy(null);
    }
  }
  function editAnnotation(index: number) {
    if (!active) return;
    setEditingAnnotationIndex(index);
    setDraft({ ...active.annotations[index], block_type: active.annotations[index].block_type || 'text' });
    setNotice('正在编辑这条证据；保存后会替换原记录。');
  }
  async function generate() {
    if (!consent) return setError('请先确认允许将选中的示例文本发送至 DeepSeek。');
    setBusy('generate');
    try {
      const next = await generateExampleRule(intent, annotatedIds);
      setRule(next);
      setRuleName(next.title);
      setNotice('规则草稿已生成。请先检查判定条件，再用示例试跑。');
    } catch (e) {
      setError(e instanceof Error ? e.message : '生成失败');
    } finally {
      setBusy(null);
      setConsent(false);
    }
  }
  async function trial() {
    if (!consent) return setError('每次试跑前都需要再次确认外发。');
    setBusy('trial');
    try {
      const result = await trialExampleRule({
        name: ruleName || rule.title,
        intent,
        definition: rule,
        document_ids: annotatedIds,
      });
      setNotice(`示例试跑已完成：${result.rule_results.map((item) => item.outcome).join('、')}。请结合原文人工复核。`);
    } catch (e) {
      setError(e instanceof Error ? e.message : '试跑失败');
    } finally {
      setBusy(null);
      setConsent(false);
    }
  }
  async function save() {
    setBusy('save');
    try {
      await createExampleRule({ name: ruleName || rule.title, intent, status: 'enabled', definition: rule });
      navigate('/example-rule-check/rules');
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setBusy(null);
    }
  }
  if (!documents) return <LoadingState label="正在加载示例规则检测…" />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="示例规则检测"
        description="把你能解释的好坏案例转化为可复用的个人检测规则。它不会影响学校规范性检测或既有报告。"
        actions={
          <>
            <Link to="/example-rule-check/rules">
              <Button variant="secondary">规则管理</Button>
            </Link>
            <Link to="/example-rule-check/reports">
              <Button variant="secondary">检测报告</Button>
            </Link>
          </>
        }
      />
      <div className="grid gap-3 md:grid-cols-3">
        {[
          ['01', '选择示例与证据'],
          ['02', '说明检查意图'],
          ['03', '验证并保存规则'],
        ].map(([n, text], i) => (
          <div
            key={n}
            className={`rounded-xl border p-4 ${i === (rule.title ? 2 : annotatedIds.length ? 1 : 0) ? 'border-brand-300 bg-brand-50' : 'border-slate-200 bg-white'}`}
          >
            <span className="text-xs font-black text-brand-600">{n}</span>
            <p className="mt-1 font-bold text-slate-800">{text}</p>
          </div>
        ))}
      </div>
      {error && <ErrorState title="本次操作未完成" message={error} />}
      {notice && (
        <div className="rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-800">{notice}</div>
      )}
      <Card
        title="建立证据集"
        description="上传 1–5 份有文字层的示例 PDF。请用“页码 + 原文摘录”记录可复核的依据。"
        actions={<StatusBadge tone={documents.length ? 'info' : 'neutral'}>{documents.length}/5 份示例</StatusBadge>}
      >
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-5 py-5 text-sm font-bold text-slate-600 hover:border-brand-400 hover:bg-brand-50">
          <Upload className="size-4" />
          添加示例 PDF
          <input
            aria-label="上传示例 PDF"
            className="sr-only"
            type="file"
            accept="application/pdf,.pdf"
            disabled={busy !== null || documents.length >= 5}
            onChange={(e) => void upload(e.target.files?.[0])}
          />
        </label>
        {documents.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="还没有示例" description="建议准备一份合格案例和一份典型问题案例，规则会更容易验证。" />
          </div>
        ) : (
          <div className="mt-5 grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)_340px]">
            <aside className="space-y-2">
              {documents.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => setActiveId(item.id)}
                  className={`w-full rounded-lg border p-3 text-left ${item.id === active?.id ? 'border-brand-400 bg-brand-50' : 'border-slate-200 hover:border-slate-300'}`}
                >
                  <p className="truncate text-sm font-bold">{item.source_filename}</p>
                  <p className="mt-1 text-xs text-slate-500">{item.annotations.length} 条证据</p>
                </button>
              ))}
            </aside>
            <div className="min-h-[520px] overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
              {pdfFile ? (
                <PdfPane
                  file={pdfFile}
                  findings={[]}
                  activeFindingKey={null}
                  activeAnchorId={null}
                  onFindingClick={() => undefined}
                  onAnchorClick={() => undefined}
                  onTextSelection={({ pageNumber, text, boundingRect }) => {
                    setDraft((current) => ({
                      ...current,
                      page_number: pageNumber,
                      text_excerpt: text,
                      bounding_rect: boundingRect,
                    }));
                    setNotice('已从 PDF 选取文本。请选择证据类型，补充说明后保存。');
                  }}
                  supplementalAnnotations={supplementalAnnotations}
                  activeSupplementalAnnotationId={
                    editingAnnotationIndex === null ? null : String(editingAnnotationIndex)
                  }
                  onSupplementalAnnotationClick={(id) => editAnnotation(Number(id))}
                />
              ) : (
                <LoadingState label="正在加载可标注的 PDF…" />
              )}
            </div>
            <section className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-2">
                <FilePlus2 className="size-4 text-brand-600" />
                <h3 className="font-bold">添加原文证据</h3>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                在左侧拖选文字即可带入页码与摘录；已有证据会在原文上高亮，点击可回到编辑。
              </p>
              <div className="mt-4 space-y-3">
                <select
                  className="w-full rounded-lg border p-2 text-sm"
                  value={draft.type}
                  onChange={(e) => setDraft((x) => ({ ...x, type: e.target.value as ExampleAnnotation['type'] }))}
                >
                  {Object.entries(labels).map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
                <select
                  className="w-full rounded-lg border p-2 text-sm"
                  value={draft.block_type || 'text'}
                  onChange={(e) =>
                    setDraft((x) => ({
                      ...x,
                      block_type: e.target.value as NonNullable<ExampleAnnotation['block_type']>,
                    }))
                  }
                >
                  <option value="text">文本</option>
                  <option value="figure">图表区域</option>
                  <option value="table">表格区域</option>
                  <option value="equation">公式区域</option>
                </select>
                <input
                  className="w-full rounded-lg border p-2 text-sm"
                  aria-label="页码"
                  type="number"
                  min="1"
                  value={draft.page_number}
                  onChange={(e) => setDraft((x) => ({ ...x, page_number: Number(e.target.value) }))}
                />
                <textarea
                  className="min-h-28 w-full rounded-lg border p-2 text-sm"
                  placeholder="从 PDF 摘录能支持判断的原文"
                  value={draft.text_excerpt}
                  onChange={(e) => setDraft((x) => ({ ...x, text_excerpt: e.target.value }))}
                />
                <input
                  className="w-full rounded-lg border p-2 text-sm"
                  placeholder="为什么这段内容重要（可选）"
                  value={draft.note}
                  onChange={(e) => setDraft((x) => ({ ...x, note: e.target.value }))}
                />
                <Button
                  className="w-full"
                  disabled={busy !== null || !draft.text_excerpt.trim()}
                  onClick={() => void annotate()}
                >
                  {editingAnnotationIndex === null ? '保存这条证据' : '更新这条证据'}
                </Button>
                {editingAnnotationIndex !== null && (
                  <Button
                    className="w-full"
                    variant="ghost"
                    disabled={busy !== null}
                    onClick={() => {
                      setEditingAnnotationIndex(null);
                      setDraft({
                        type: 'focus',
                        block_type: 'text',
                        page_number: draft.page_number,
                        text_excerpt: '',
                        note: '',
                      });
                    }}
                  >
                    取消编辑
                  </Button>
                )}
              </div>
              {active.annotations.length > 0 && (
                <div className="mt-5 border-t border-slate-200 pt-4">
                  <p className="text-xs font-bold text-slate-700">当前示例的证据（{active.annotations.length}）</p>
                  <div className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
                    {active.annotations.map((annotation, index) => (
                      <div
                        key={`${annotation.page_number}-${index}`}
                        className={`rounded-lg border p-3 ${editingAnnotationIndex === index ? 'border-brand-400 bg-brand-50' : 'border-slate-200 bg-white'}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <button type="button" className="min-w-0 text-left" onClick={() => editAnnotation(index)}>
                            <p className="text-xs font-bold text-slate-800">
                              {labels[annotation.type]} · {blockLabels[annotation.block_type || 'text']} · 第{' '}
                              {annotation.page_number} 页
                            </p>
                            <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">
                              {annotation.text_excerpt}
                            </p>
                          </button>
                          <div className="flex shrink-0 items-center gap-1">
                            <button
                              type="button"
                              className="rounded p-1 text-slate-500 hover:bg-slate-100"
                              aria-label="编辑证据"
                              onClick={() => editAnnotation(index)}
                            >
                              <Pencil className="size-3.5" />
                            </button>
                            <button
                              type="button"
                              className="rounded p-1 text-danger-600 hover:bg-danger-50"
                              aria-label="删除证据"
                              disabled={busy !== null}
                              onClick={() => void removeAnnotation(index)}
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </Card>
      <Card title="把证据转成检查意图" description="用自己的话说明希望发现什么；系统不会替你猜测业务标准。">
        <textarea
          className="min-h-28 w-full rounded-xl border border-slate-300 p-3 text-sm"
          placeholder="例如：检查实验结果中的关键结论是否有相应数据、图表或公式支撑"
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
        />
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 p-3">
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input className="mt-1" type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>
              <b>允许本次外发</b>
              <br />
              仅会向 DeepSeek 发送选中的示例证据和检查意图。
            </span>
          </label>
          <Button
            disabled={busy !== null || !intent.trim() || annotatedIds.length === 0 || !consent}
            onClick={() => void generate()}
          >
            {busy === 'generate' ? (
              '正在生成…'
            ) : (
              <>
                <Sparkles className="size-4" />
                生成规则草稿
              </>
            )}
          </Button>
        </div>
      </Card>
      {rule.title && (
        <Card
          title="审阅并验证规则"
          description="先检查规则的可解释性，再通过示例试跑决定是否保存。"
          actions={<StatusBadge tone="warning">人工复核必需</StatusBadge>}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <input
                className="w-full rounded-lg border p-2 text-sm font-bold"
                placeholder="规则名称"
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
              />
              <textarea
                className="min-h-28 w-full rounded-lg border p-2 text-sm"
                value={rule.check_description}
                onChange={(e) => setRule((x) => ({ ...x, check_description: e.target.value }))}
              />
              <textarea
                className="min-h-36 w-full rounded-lg border p-2 text-sm"
                placeholder="每行一条判定条件"
                value={rule.criteria.join('\n')}
                onChange={(e) => setRule((x) => ({ ...x, criteria: e.target.value.split('\n').filter(Boolean) }))}
              />
            </div>
            <div className="rounded-xl bg-slate-50 p-5">
              <Lightbulb className="size-5 text-brand-600" />
              <h3 className="mt-3 font-bold">保存前检查</h3>
              <ul className="mt-2 space-y-2 text-sm text-slate-600">
                <li>• 是否能从证据中看出“通过”和“问题”的区别？</li>
                <li>• 是否已写明不适用或例外的情况？</li>
                <li>• 是否需要更多代表性示例？</li>
              </ul>
              <label className="mt-5 flex gap-2 text-sm">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                确认本次试跑允许外发
              </label>
              <div className="mt-4 flex gap-3">
                <Button variant="secondary" disabled={busy !== null || !consent} onClick={() => void trial()}>
                  {busy === 'trial' ? (
                    '试跑中…'
                  ) : (
                    <>
                      <FlaskConical className="size-4" />
                      示例试跑
                    </>
                  )}
                </Button>
                <Button disabled={busy !== null} onClick={() => void save()}>
                  {busy === 'save' ? '保存中…' : '保存个人规则'}
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <LockKeyhole className="size-3.5" />
        示例、规则和报告仅对当前创建者可见。
      </div>
    </div>
  );
}
