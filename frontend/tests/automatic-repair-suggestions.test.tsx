import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { usePaperLintRepairSuggestions } from '../src/hooks/usePaperLintRepairSuggestions';
import { fetchPaperLintFindingRepairSuggestion, evaluatePaperLintFindingRepairSuggestion } from '../src/api/repairSuggestions';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
vi.mock('../src/api/repairSuggestions',()=>({PAPER_LINT_REPAIR_RULE_IDS:new Set(['sjtu_rule_31']),fetchPaperLintFindingRepairSuggestion:vi.fn(),evaluatePaperLintFindingRepairSuggestion:vi.fn()}));
const item=(id:string)=>({key:id,ruleRun:{rule_id:'sjtu_rule_31',severity:'warning'},finding:{finding_id:id,message:id,anchors:[]}} as PaperLintFindingItem);
const suggestion=(id:string)=>({schema_version:'repair-response-v2',rule_id:'sjtu_rule_31',finding_id:id,status:'suggested',actions:[{instruction:'补全文献类型标识 '+id,evidence_ids:[]}],provenance:{model:'model',prompt_version:'v2'}} as any);
beforeEach(()=>vi.resetAllMocks());
it('shows saved advice on inactive cards and loads every finding without a click',()=>{
 const items=[item('a'),item('b')];const load=vi.fn();
 render(<FindingsPane findings={items} rules={[]} activeFindingKey="a" activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} onLoadRepairSuggestion={load} onGenerateRepairSuggestion={vi.fn()} repairSuggestionByFindingKey={{a:suggestion('a'),b:suggestion('b')}} />);
 expect(screen.getByText('补全文献类型标识 b')).toBeInTheDocument();
 expect(load.mock.calls.map(([x])=>x.key)).toEqual(['a','b']);
 expect(screen.getAllByRole('button',{name:'重新生成修复建议'})).toHaveLength(2);
});
it('generates missing advice automatically and keeps explicit regeneration available',async()=>{
 vi.mocked(fetchPaperLintFindingRepairSuggestion).mockResolvedValueOnce(null).mockResolvedValueOnce(suggestion('b'));
 vi.mocked(evaluatePaperLintFindingRepairSuggestion).mockResolvedValue({response:suggestion('a'),cached:false});
 const {result}=renderHook(()=>usePaperLintRepairSuggestions('report'));
 await act(async()=>{await Promise.all([result.current.loadRepairSuggestion(item('a')),result.current.loadRepairSuggestion(item('b'))]);});
 expect(result.current.repairSuggestionByFindingKey.a?.actions[0].instruction).toContain('a');
 expect(result.current.repairSuggestionByFindingKey.b?.actions[0].instruction).toContain('b');
 expect(evaluatePaperLintFindingRepairSuggestion).toHaveBeenCalledWith(expect.objectContaining({finding_id:'a'}),{force:false});
 await act(async()=>{await result.current.generateRepairSuggestion(item('a'));});
 expect(result.current.repairSuggestionByFindingKey.a?.actions[0].instruction).toContain('a');
 expect(evaluatePaperLintFindingRepairSuggestion).toHaveBeenCalledWith(expect.objectContaining({finding_id:'a'}),{force:true});
});
it('bounds automatic loading and does not retry failures on rerender',async()=>{
 let active=0,max=0;const finish:(()=>void)[]=[];
 vi.mocked(fetchPaperLintFindingRepairSuggestion).mockImplementation(()=>new Promise(resolve=>{active++;max=Math.max(max,active);finish.push(()=>{active--;resolve(suggestion('x'));});}));
 const {result}=renderHook(()=>usePaperLintRepairSuggestions('report'));
 let work:Promise<void>[]=[];act(()=>{work=Array.from({length:8},(_,i)=>result.current.loadRepairSuggestion(item(String(i))));});
 await waitFor(()=>expect(active).toBeGreaterThan(0));expect(max).toBeLessThanOrEqual(3);
 await act(async()=>{while(finish.length||active){finish.splice(0).forEach(f=>f());await new Promise(resolve=>setTimeout(resolve,0));}await Promise.all(work);});
 expect(max).toBeLessThanOrEqual(3);
});
it('preserves a generation error without retrying on cache reads',async()=>{
 vi.mocked(fetchPaperLintFindingRepairSuggestion).mockResolvedValue(null);vi.mocked(evaluatePaperLintFindingRepairSuggestion).mockRejectedValue(new Error('预算已达到上限'));
 const {result,rerender}=renderHook(()=>usePaperLintRepairSuggestions('report'));
 await act(async()=>{await result.current.generateRepairSuggestion(item('a'));});rerender();
 await act(async()=>{await result.current.loadRepairSuggestion(item('a'));});
 expect(result.current.repairSuggestionErrorByFindingKey.a).toContain('预算');expect(evaluatePaperLintFindingRepairSuggestion).toHaveBeenCalledTimes(1);
});

it('shows cached advice without waiting for unrelated paid generations',async()=>{
 const finish:(()=>void)[]=[];
 vi.mocked(fetchPaperLintFindingRepairSuggestion).mockImplementation(async reference=>reference.finding_id==='cached'?suggestion('cached'):null);
 vi.mocked(evaluatePaperLintFindingRepairSuggestion).mockImplementation(async reference=>new Promise(resolve=>finish.push(()=>resolve({response:suggestion(reference.finding_id),cached:false}))));
 const {result}=renderHook(()=>usePaperLintRepairSuggestions('report'));
 let work:Promise<void>[]=[];act(()=>{work=['a','b','c','cached'].map(id=>result.current.loadRepairSuggestion(item(id)));});
 try {await waitFor(()=>expect(result.current.repairSuggestionByFindingKey.cached?.finding_id).toBe('cached'),{timeout:300});}
 finally {await act(async()=>{while(finish.length){finish.splice(0).forEach(f=>f());await new Promise(resolve=>setTimeout(resolve,0));}await Promise.all(work);});}
});
