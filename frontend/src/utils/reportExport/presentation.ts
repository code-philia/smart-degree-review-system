import { createTranslator, getLocale } from '../../i18n/locale.js';
import type { ExportFinding, ExportReport, ReportBlock } from './model';

type Translator = ((value: string) => string) & { has?: (value: string) => boolean };
const blockPresentation = Symbol('export block presentation');
const reportPresentation = Symbol('export report presentation');
const rulesetPresentation = Symbol('export generated ruleset presentation');
type RulesetDescriptor = { id: string; name: string; version_number: number; version_label: string };
type GeneratedRuleset = { compilerVersionSource: string | null };
type MarkedRulesetReport = ExportReport & { [rulesetPresentation]?: GeneratedRuleset };
export function markRulesetPresentation(model: ExportReport, ruleset: RulesetDescriptor): ExportReport {
  // reviewPilotPaperLintService.mergePaperLintResults owns this descriptor.
  // Match its identity as well as its known generated format; a catalog's
  // actual version label with identical words remains original metadata.
  if (
    ruleset.id !== 'smart-degree-combined-pdf-lint' ||
    ruleset.name !== '基础规则检测' ||
    ruleset.version_number !== 1
  )
    return model;
  const prefix = '当前本地版本',
    compilerPrefix = prefix + ' · 引用规则 ';
  const generated =
    ruleset.version_label === prefix
      ? { compilerVersionSource: null }
      : ruleset.version_label.startsWith(compilerPrefix) && ruleset.version_label.length > compilerPrefix.length
        ? { compilerVersionSource: ruleset.version_label.slice(compilerPrefix.length) }
        : null;
  if (!generated) return model;
  const marked = { ...model, [rulesetPresentation]: generated };
  return marked;
}
function localizedRuleset(model: ExportReport, t: Translator): string {
  const generated = (model as MarkedRulesetReport)[rulesetPresentation];
  if (!generated) return model.ruleset;
  return (
    t('当前本地版本') +
    (generated.compilerVersionSource === null ? '' : ` · ${t('引用规则')} ${generated.compilerVersionSource}`)
  );
}
const findingSources = Symbol('export finding sources');
export function markFindingSources(
  finding: ExportFinding,
  basisSourceIndices: number[],
  suggestionSourceIndices: number[] = [],
): ExportFinding {
  const marked = {
    ...finding,
    [findingSources]: {
      basis: new Set(basisSourceIndices),
      suggestions: new Set(suggestionSourceIndices),
    },
  };
  return marked;
}
type MarkedFinding = ExportFinding & { [findingSources]?: { basis: Set<number>; suggestions: Set<number> } };
function sourceBasis(finding: ExportFinding, index: number): boolean {
  return (finding as MarkedFinding)[findingSources]?.basis.has(index) ?? false;
}
function sourceSuggestion(finding: ExportFinding, index: number): boolean {
  return (finding as MarkedFinding)[findingSources]?.suggestions.has(index) ?? false;
}
type BlockPresentation = { english: (t: Translator) => string; required: string[] };
type MarkedBlock = ReportBlock & { [blockPresentation]?: BlockPresentation };
type PresentedReport = ExportReport & { [reportPresentation]?: { locale: 'en'; translate: Translator } };
// Symbol metadata records provenance while leaving all original JSON fields untouched.
export function presentationBlock(
  block: ReportBlock,
  english: (t: Translator) => string,
  required: string[],
): ReportBlock {
  const marked = { ...block, [blockPresentation]: { english, required } };
  return marked;
}
export function blockTranslationTexts(block: ReportBlock): string[] {
  const metadata = (block as MarkedBlock)[blockPresentation];
  return metadata?.required ?? (block.kind === 'quote' ? [] : [block.text]);
}
export function translateBlock(block: ReportBlock, t: Translator): ReportBlock {
  const metadata = (block as MarkedBlock)[blockPresentation];
  if (metadata?.english) return { ...block, text: metadata.english(t) };
  return block.kind === 'quote' ? block : { ...block, text: t(block.text) };
}
export function reportTranslator(model: ExportReport): Translator | undefined {
  return (model as PresentedReport)[reportPresentation]?.translate;
}
export function reportLocale(model: ExportReport): 'en' | 'zh' {
  return (model as PresentedReport)[reportPresentation]?.locale ?? 'zh';
}
export function collectExportTranslationTexts(model: ExportReport): string[] {
  return [
    ...new Set(
      [
        model.detection_type,
        model.conclusion,
        model.notice,
        ...model.scope.flatMap((rule) => [rule.title, rule.description]),
        ...model.findings.flatMap((item) => [
          item.rule_title,
          item.severity,
          item.message,
          ...item.suggestions.filter((_, index) => !sourceSuggestion(item, index)),
          ...item.basis.filter((_, index) => !sourceBasis(item, index)),
          ...item.locations.map((location) => location.label),
        ]),
        ...model.rules.flatMap((rule) => [
          rule.title,
          rule.status,
          rule.message,
          ...rule.details.flatMap(blockTranslationTexts),
        ]),
      ].filter(Boolean),
    ),
  ];
}
export function localizeExportReport(
  model: ExportReport,
  locale = getLocale(),
  translate: Translator = createTranslator(locale),
): ExportReport {
  if (locale !== 'en' || reportLocale(model) === 'en') return model;
  const t = translate;
  return {
    ...model,
    [reportPresentation]: { locale: 'en', translate: t },
    detection_type: t(model.detection_type),
    ruleset: localizedRuleset(model, t),
    conclusion: t(model.conclusion),
    notice: t(model.notice),
    scope: model.scope.map((rule) => ({ ...rule, title: t(rule.title), description: t(rule.description) })),
    findings: model.findings.map((item) => ({
      ...item,
      rule_title: t(item.rule_title),
      severity: t(item.severity),
      message: t(item.message),
      suggestions: item.suggestions.map((text, index) => (sourceSuggestion(item, index) ? text : t(text))),
      basis: item.basis.map((text, index) => (sourceBasis(item, index) ? text : t(text))),
      locations: item.locations.map((location) => ({ ...location, label: t(location.label) })),
    })),
    rules: model.rules.map((rule) => ({
      ...rule,
      title: t(rule.title),
      status: t(rule.status),
      message: t(rule.message),
      details: rule.details.map((block) => translateBlock(block, t)),
    })),
  } as ExportReport;
}
