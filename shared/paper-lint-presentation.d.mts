import type { PaperLintResult, PaperLintRuleRun, PaperLintSummary } from '../frontend/src/api/paperLint';
export function referenceInfoFindings(run: PaperLintRuleRun): import('../frontend/src/api/paperLint').PaperLintFinding[];
export function referenceResourcesUnavailable(run: PaperLintRuleRun): boolean;
export function isGenericExecutionWarning(run: PaperLintRuleRun): boolean;
export function chapterPrerequisiteSuggestion(run: PaperLintRuleRun): string | null;
export function displayedReportSummary(result: Pick<PaperLintResult, 'rule_runs' | 'summary'>): PaperLintSummary;

export type ExecutionWarningFeedbackTarget = { findingId: string; kind: 'precondition' | 'failure' | 'generic'; preconditionIndex?: number };
export function executionWarningFeedbackTargets(run: PaperLintRuleRun): ExecutionWarningFeedbackTarget[];
