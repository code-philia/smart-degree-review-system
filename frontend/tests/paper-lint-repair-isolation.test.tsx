import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { usePaperLintRepairSuggestions } from '../src/hooks/usePaperLintRepairSuggestions';
import { fetchPaperLintFindingRepairSuggestion, evaluatePaperLintFindingRepairSuggestion } from '../src/api/repairSuggestions';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
vi.mock('../src/api/repairSuggestions', () => ({
  PAPER_LINT_REPAIR_RULE_IDS:new Set(['sjtu_rule_15']),
  fetchPaperLintFindingRepairSuggestion:vi.fn(), evaluatePaperLintFindingRepairSuggestion:vi.fn(),
}));
beforeEach(() => vi.clearAllMocks());
const item={key:'same-finding',ruleRun:{rule_id:'sjtu_rule_15'},finding:{finding_id:'same-finding'}} as PaperLintFindingItem;
it.each(['load','generate'])('does not put an old report %s response into the newly opened report', async (kind) => {
  let finish:(value:any)=>void = () => {};
  const pending=new Promise<any>((resolve) => {finish=resolve;});
  vi.mocked(fetchPaperLintFindingRepairSuggestion).mockReturnValue(pending);
  vi.mocked(evaluatePaperLintFindingRepairSuggestion).mockReturnValue(pending);
  const {result,rerender}=renderHook(({id})=>usePaperLintRepairSuggestions(id),{initialProps:{id:'report-A'}});
  let work:Promise<void>;
  act(()=>{work=kind==='load'?result.current.loadRepairSuggestion(item):result.current.generateRepairSuggestion(item);});
  rerender({id:'report-B'});
  await act(async()=>{finish(kind==='load'?{status:'suggested'}:{response:{status:'suggested'}});await work;});
  expect(result.current.repairSuggestionByFindingKey).toEqual({});
  expect(result.current.repairSuggestionLoadingKey).toBeNull();
});
