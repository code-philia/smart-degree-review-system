import { act, render, renderHook, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useFindingRepairSuggestions } from '../src/hooks/useFindingRepairSuggestions';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
const item = (id: string) => ({key:id,ruleRun:{rule_id:'sjtu_rule_31',severity:'warning'},finding:{finding_id:id,message:id,anchors:[]}} as PaperLintFindingItem);
const advice = (id: string) => ({schema_version:'repair-response-v2',rule_id:'sjtu_rule_31',finding_id:id,status:'suggested',actions:[{instruction:'已保存建议 '+id,evidence_ids:[]}],provenance:{model:'model',prompt_version:'repair-model-actions-v2'}} as any);
it('settles an archive cache miss without generating, showing an error, or retrying on rerender', async () => {
  const fetchSaved=vi.fn(async()=>null);
  const {result,rerender}=renderHook(()=>useFindingRepairSuggestions({scopeKey:'archive:doc',fetchSaved} as any));
  await act(async()=>{await result.current.loadRepairSuggestion(item('missing'));});
  expect(result.current.repairSuggestionErrorByFindingKey.missing).toBeUndefined();
  expect(result.current.repairSuggestionLoadingByFindingKey.missing).toBe(false);
  rerender();
  await act(async()=>{await result.current.loadRepairSuggestion(item('missing'));});
  expect(fetchSaved).toHaveBeenCalledTimes(1);
});
it('shows all saved archive suggestions without generation buttons, including inactive citation cards', () => {
  const load=vi.fn();
  render(<FindingsPane findings={[item('a'),item('b')]} rules={[]} activeFindingKey="a" activeAnchorId={null}
    onFindingClick={vi.fn()} onAnchorClick={vi.fn()} onLoadRepairSuggestion={load}
    repairSuggestionByFindingKey={{a:advice('a'),b:advice('b')}} />);
  expect(screen.getByText('已保存建议 a')).toBeInTheDocument();
  expect(screen.getByText('已保存建议 b')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/生成.*修复建议/})).not.toBeInTheDocument();
  expect(load.mock.calls.map(([value])=>value.key)).toEqual(['a','b']);
});
