import { ArrowRight, Check, ChevronDown, FileText, LoaderCircle, ShieldCheck, Square, Upload, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { PaperLintRule } from '../../api/paperLint';
import { Button } from '../ui';

type Props = {
  rules: PaperLintRule[];
  selectedRuleIds: string[];
  onSelectionChange: (ids: string[]) => void;
  file: File | null;
  onChooseFile: (file: File | null) => void;
  catalogLoading: boolean;
  catalogReady: boolean;
  catalogError: string | null;
  onReloadCatalog: () => void;
  running: boolean;
  stopping: boolean;
  stopped: boolean;
  canStop: boolean;
  onStop: () => void;
  onStart: () => void;
  error: string | null;
  uploadPercent: number | null;
  jobStatus: 'pending' | 'running' | null;
  jobProgress: { completed: number; total: number } | null;
  activeFilename: string | null;
  requiresConsent: boolean;
  consent: boolean;
  onConsentChange: (value: boolean) => void;
};

const GROUPS = ['格式排版', '文字表述', '语言规范'] as const;
function ruleGroup(id: string) {
  if (['typo_detection_check', 'bilingual_abstract_consistency_check'].includes(id)) return '文字表述';
  if (['chinese_english_symbol_mix_check', 'bilingual_keywords_correspondence_check'].includes(id)) return '语言规范';
  return '格式排版';
}

function DetectionProgress({
  uploadPercent,
  jobStatus,
  jobProgress,
  activeFilename,
}: Pick<Props, 'uploadPercent' | 'jobStatus' | 'jobProgress' | 'activeFilename'>) {
  const uploading = uploadPercent !== null;
  const phase = uploading ? 0 : jobStatus === 'running' ? 2 : 1;
  const stages = ['正在上传', '开始解析', '开始检测', '检测完成'];
  const percent = uploading ? Math.max(0, Math.min(100, uploadPercent)) : null;
  const text = percent === null ? stages[phase] : `正在上传，${percent}%`;
  const circumference = 2 * Math.PI * 42;
  return (
    <section aria-label="检测任务状态" className="mt-5 rounded-2xl border border-brand-100 bg-brand-50/40 p-5 sm:p-6">
      <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
        <div
          role="progressbar"
          aria-label="检测进度"
          aria-valuetext={text}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
          className="relative size-24 shrink-0"
        >
          <svg
            viewBox="0 0 100 100"
            className={`size-full -rotate-90 ${percent === null ? 'animate-spin [animation-duration:2s] motion-reduce:animate-none' : ''}`}
            aria-hidden="true"
          >
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="currentColor"
              strokeWidth="5"
              className="text-brand-100"
            />
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="currentColor"
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={percent === null ? `${circumference * 0.24} ${circumference * 0.76}` : circumference}
              strokeDashoffset={percent === null ? 0 : circumference * (1 - percent / 100)}
              className="text-brand-600 transition-[stroke-dashoffset] duration-300 motion-reduce:transition-none"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-lg font-semibold tabular-nums text-brand-700">
            {percent === null ? <FileText className="size-6" /> : `${percent}%`}
          </span>
        </div>
        <div className="min-w-0 flex-1 text-center sm:text-left" role="status">
          <p className="text-lg font-semibold text-slate-900">{stages[phase]}</p>
          {activeFilename ? (
            <p className="mt-1 truncate text-sm text-slate-600" title={activeFilename}>
              {activeFilename}
            </p>
          ) : null}
          <p className="mt-2 text-sm leading-6 text-slate-500">
            {phase === 0
              ? '正在传输论文文件，上传后将提交后台处理。'
              : phase === 1
                ? '论文已上传，正在等待后台解析和检测。'
                : jobProgress?.total
                  ? `后台检测已开始，已完成 ${jobProgress.completed} / ${jobProgress.total} 项规则。`
                  : '后台检测已开始，正在解析论文并执行所选规则。'}
          </p>
          {phase > 0 ? (
            <p className="mt-1 text-xs leading-5 text-slate-500">
              你可以离开页面，稍后从论文上传页恢复查看，完成的报告将保存在历史报告中。
            </p>
          ) : null}
        </div>
      </div>
      <ol className="mt-5 grid grid-cols-2 gap-3 border-t border-brand-100 pt-4 sm:grid-cols-4" aria-label="检测阶段">
        {stages.map((label, index) => (
          <li
            key={label}
            aria-current={index === phase ? 'step' : undefined}
            className={`flex items-center gap-2 text-xs ${index === phase ? 'font-semibold text-brand-700' : index < phase ? 'text-emerald-700' : 'text-slate-400'}`}
          >
            <span
              className={`flex size-5 shrink-0 items-center justify-center rounded-full border ${index === phase ? 'border-brand-500 bg-brand-600 text-white' : index < phase ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-white'}`}
            >
              {index < phase ? <Check className="size-3" /> : index + 1}
            </span>
            {label}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ThesisUploadPanel(props: Props) {
  const {
    rules,
    selectedRuleIds,
    onSelectionChange,
    file,
    onChooseFile,
    catalogLoading,
    catalogReady,
    catalogError,
    onReloadCatalog,
    running,
    stopping,
    stopped,
    canStop,
    onStop,
    onStart,
    error,
    requiresConsent,
    consent,
    onConsentChange,
  } = props;
  const [expanded, setExpanded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const progressRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!running) return;
    setExpanded(false);
    const frame = requestAnimationFrame(() => {
      progressRef.current?.scrollIntoView?.({
        block: 'nearest',
        behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [running]);
  const ruleRegion = useId();
  const busy = running || stopping;
  const available = rules.filter((rule) => rule.available);
  const selected = new Set(selectedRuleIds);
  const unavailableSelection = selectedRuleIds.some((id) => !available.some((rule) => rule.rule_id === id));
  const allSelected = available.length > 0 && available.every((rule) => selected.has(rule.rule_id));
  const selectedSummary = allSelected
    ? available.length === rules.length
      ? '已选择全部检测规则'
      : '已选择全部可用检测规则'
    : `已选择 ${selectedRuleIds.length} 项检测规则`;
  const noSelection = catalogReady && !catalogLoading && !selectedRuleIds.length;
  const filename = file?.name || (busy ? props.activeFilename : null);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pt-1">
        <div>
          <p className="mb-1 text-xs font-medium tracking-wider text-brand-600">论文规范性检测</p>
          <h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">论文上传</h1>
        </div>
        <Link
          to="/thirty-rules-check/reports"
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-white hover:text-brand-700"
        >
          查看历史报告
          <ArrowRight className="size-4" />
        </Link>
      </header>

      <section
        aria-label="论文上传与检测设置"
        className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_12px_40px_-28px_rgba(15,23,42,.3)]"
      >
        <div className="p-5 sm:p-7">
          <div className="mb-4 flex items-center gap-2.5">
            <span className="text-xs font-semibold tabular-nums text-brand-600">01</span>
            <h2 className="text-sm font-semibold text-slate-900">上传论文</h2>
          </div>
          <label
            className={`flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed px-5 py-7 text-center transition sm:min-h-60 ${busy ? 'cursor-not-allowed border-slate-200 bg-slate-50/70' : dragging ? 'cursor-pointer border-brand-500 bg-brand-50' : 'cursor-pointer border-slate-300 bg-slate-50/60 hover:border-brand-400 hover:bg-brand-50/40 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100'}`}
            aria-disabled={busy}
            onDragEnter={(event) => {
              event.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (!busy) onChooseFile(event.dataTransfer.files?.[0] || null);
            }}
          >
            <input
              className="sr-only"
              type="file"
              accept=".pdf,application/pdf"
              aria-label="上传待审查 PDF"
              disabled={busy}
              onChange={(event) => {
                onChooseFile(event.currentTarget.files?.[0] || null);
                event.currentTarget.value = '';
              }}
            />
            <span className="flex size-14 items-center justify-center rounded-2xl border border-brand-100 bg-white text-brand-600 shadow-sm">
              {filename ? <FileText className="size-7" /> : <Upload className="size-7" />}
            </span>
            {filename ? (
              <>
                <span className="mt-4 max-w-full break-all text-base font-semibold text-slate-900">{filename}</span>
                <span className="mt-2 text-xs text-slate-500">
                  {file
                    ? file.size >= 1024 * 1024
                      ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
                      : `${Math.ceil(file.size / 1024)} KB`
                    : '已恢复后台任务'}
                </span>
              </>
            ) : (
              <>
                <span className="mt-4 text-base font-semibold text-slate-800">点击或将文件拖拽至此处上传</span>
                <span className="mt-2 max-w-xl text-xs leading-6 text-slate-500 sm:text-sm">
                  支持 pdf 格式（扫描版 pdf 除外），文件大小不超过 50MB；支持中英文检测
                </span>
              </>
            )}
          </label>
          {file ? (
            <div className="mt-2 flex justify-end">
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => onChooseFile(null)}>
                <X className="size-3.5" />
                移除文件
              </Button>
            </div>
          ) : null}
        </div>

        <section aria-label="检测规则选择" className="border-t border-slate-100 px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-semibold tabular-nums text-brand-600">02</span>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">检测规则</h2>
                <p className="mt-1 text-xs text-slate-500" aria-live="polite">
                  {catalogLoading ? '正在读取检测规则…' : catalogReady ? selectedSummary : '检测规则暂未加载'}
                </p>
              </div>
              {catalogReady && !catalogLoading ? (
                <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs tabular-nums text-slate-600">
                  {selectedRuleIds.length} / {available.length}
                </span>
              ) : null}
            </div>
            <Button
              size="sm"
              variant="ghost"
              aria-expanded={expanded}
              aria-controls={ruleRegion}
              disabled={busy || !catalogReady}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? '收起选择' : '展开选择'}
              <ChevronDown className={`size-4 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`} />
            </Button>
          </div>
          {catalogError ? (
            <div role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">
              {catalogError}
              <Button size="sm" variant="ghost" className="ml-2" onClick={onReloadCatalog}>
                重新加载
              </Button>
            </div>
          ) : null}
          {expanded ? (
            <div
              id={ruleRegion}
              className="mt-5 animate-in fade-in slide-in-from-top-1 duration-200 motion-reduce:animate-none"
            >
              <div className="mb-3 flex justify-end gap-1">
                <Button
                  aria-label="全选全部检测规则"
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => onSelectionChange(available.map((rule) => rule.rule_id))}
                >
                  全选
                </Button>
                <Button
                  aria-label="清空全部检测规则"
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => onSelectionChange([])}
                >
                  清空
                </Button>
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                {GROUPS.map((group) => {
                  const groupRules = rules.filter((rule) => ruleGroup(rule.rule_id) === group);
                  const ids = groupRules.filter((rule) => rule.available).map((rule) => rule.rule_id);
                  return (
                    <section
                      key={group}
                      aria-label={`${group}检测规则`}
                      className="rounded-2xl border border-slate-200 bg-slate-50/40"
                    >
                      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-3">
                        <h3 className="whitespace-nowrap text-sm font-semibold text-slate-800">{group}</h3>
                        <div className="flex">
                          <Button
                            size="sm"
                            variant="ghost"
                            className="px-1.5 text-xs"
                            aria-label={`全选${group}`}
                            disabled={busy || !ids.length}
                            onClick={() => onSelectionChange([...new Set([...selectedRuleIds, ...ids])])}
                          >
                            全选
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="px-1.5 text-xs"
                            aria-label={`清空${group}`}
                            disabled={busy || !ids.length}
                            onClick={() => onSelectionChange(selectedRuleIds.filter((id) => !ids.includes(id)))}
                          >
                            清空
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-1 p-2">
                        {groupRules.length ? (
                          groupRules.map((rule) => (
                            <label
                              key={rule.rule_id}
                              className={`flex items-start gap-2.5 rounded-xl p-2.5 transition ${!rule.available ? 'cursor-not-allowed opacity-60' : busy ? '' : 'cursor-pointer hover:bg-white'} ${selected.has(rule.rule_id) ? 'bg-white' : ''}`}
                            >
                              <input
                                type="checkbox"
                                className="mt-0.5 size-4 shrink-0 accent-brand-600"
                                checked={selected.has(rule.rule_id)}
                                disabled={busy || !rule.available}
                                onChange={() =>
                                  onSelectionChange(
                                    selected.has(rule.rule_id)
                                      ? selectedRuleIds.filter((id) => id !== rule.rule_id)
                                      : [...selectedRuleIds, rule.rule_id],
                                  )
                                }
                              />
                              <span className="min-w-0">
                                <span className="block text-xs font-medium leading-5 text-slate-800">{rule.title}</span>
                                <span className="mt-1 block text-[11px] leading-5 text-slate-500">
                                  {rule.description}
                                </span>
                                {!rule.available ? (
                                  <span className="mt-1 block text-[11px] leading-5 text-amber-700">
                                    {rule.availability_reason || '该规则暂不可用'}
                                  </span>
                                ) : null}
                              </span>
                            </label>
                          ))
                        ) : (
                          <p className="px-2.5 py-3 text-xs text-slate-400">暂无已开放规则</p>
                        )}
                      </div>
                    </section>
                  );
                })}
              </div>
            </div>
          ) : null}
          {noSelection ? (
            <p role="alert" className="mt-3 text-xs text-amber-700">
              {available.length ? '请至少选择一项检测规则' : '当前暂无可用检测规则，请稍后重试或联系管理员。'}
            </p>
          ) : null}
          {unavailableSelection && !busy ? (
            <p role="alert" className="mt-3 text-xs text-amber-700">
              部分已选规则暂不可用，请展开重新选择。
            </p>
          ) : null}
        </section>

        <div className="border-t border-slate-100 bg-slate-50/40 px-5 py-4 sm:px-7">
          {requiresConsent ? (
            <label className="mb-4 flex items-start gap-2.5 rounded-xl border border-brand-100 bg-white px-3 py-3 text-xs leading-5 text-slate-600">
              <input
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-brand-600"
                checked={consent}
                onChange={(event) => onConsentChange(event.target.checked)}
                disabled={busy}
              />
              <span>我确认本次论文相关文本允许发送至校内 DeepSeek API进行语义检测。</span>
            </label>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="flex items-center gap-1.5 text-xs text-slate-500">
              <ShieldCheck className="size-4 text-brand-500" />
              请确认论文版本及本次检测范围
            </p>
            <div className="flex gap-2">
              {busy ? (
                <Button
                  variant="ghost"
                  disabled={!canStop || stopping}
                  title={!canStop ? '上传完成后可停止检测' : undefined}
                  onClick={onStop}
                >
                  {stopping ? <LoaderCircle className="size-4 animate-spin" /> : <Square className="size-3.5" />}
                  {stopping ? '正在停止…' : '停止检测'}
                </Button>
              ) : null}
              <Button
                className="min-w-32 rounded-xl px-6"
                disabled={
                  !file ||
                  !catalogReady ||
                  catalogLoading ||
                  noSelection ||
                  unavailableSelection ||
                  busy ||
                  (requiresConsent && !consent)
                }
                onClick={onStart}
              >
                {busy ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
                {busy ? '检测进行中' : '开始检测'}
              </Button>
            </div>
          </div>
        </div>
      </section>
      {error ? (
        <div
          role="alert"
          className="rounded-2xl border border-red-100 bg-red-50 px-5 py-4 text-sm leading-6 text-red-700"
        >
          {error}
        </div>
      ) : null}
      {stopped && !running ? (
        <p role="status" className="px-1 text-sm text-slate-600">
          已停止检测，可以重新开始。
        </p>
      ) : null}
      {running ? (
        <div ref={progressRef}>
          <DetectionProgress {...props} />
        </div>
      ) : null}
      <aside aria-label="检测说明" className="px-1 pb-3 text-xs leading-6 text-slate-500">
        <p>
          聚焦公式引用、文献引用与目录页码等可定位问题。上传论文后，您可自主选择已开放规则，逐项查看检测结果，并联动定位到论文原文位置。受算力资源限制，每位用户累计检测次数不超过
          3 次，请提前确认论文版本、合理勾选检测规则。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议。
        </p>
      </aside>
    </div>
  );
}
