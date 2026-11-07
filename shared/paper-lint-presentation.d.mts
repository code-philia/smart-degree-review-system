import type { PaperLintResult, PaperLintRuleRun, PaperLintSummary } from '../frontend/src/api/paperLint';
export function referenceResourcesUnavailable(run: PaperLintRuleRun): boolean;
export function isGenericExecutionWarning(run: PaperLintRuleRun): boolean;
export function chapterPrerequisiteSuggestion(run: PaperLintRuleRun): string | null;
export function displayedReportSummary(result: Pick<PaperLintResult, 'rule_runs' | 'summary'>): PaperLintSummary;
