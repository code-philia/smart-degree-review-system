import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { PAPER_LINT_REPAIR_RULE_IDS } from '../src/api/repairSuggestions';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
it.each(['31','32','33'])('shows and triggers AI repair for citation rule%s', id=>{
 const item={key:'f1',ruleRun:{rule_id:`sjtu_rule_${id}`,severity:'warning'},finding:{finding_id:'f1',message:'引用问题',anchors:[]}} as PaperLintFindingItem;
 const generate=vi.fn();render(<FindingsPane findings={[item]} rules={[]} activeFindingKey="f1" activeAnchorId={null}
  onFindingClick={vi.fn()} onAnchorClick={vi.fn()} onGenerateRepairSuggestion={generate}
  supportsRepairSuggestion={x=>PAPER_LINT_REPAIR_RULE_IDS.has(x.ruleRun.rule_id)} />);
 fireEvent.click(screen.getByRole('button',{name:'生成 AI 修复建议'}));expect(generate).toHaveBeenCalledWith(item);
});
it('retains the ten existing rules and excludes unrelated rules',()=>{
 expect(PAPER_LINT_REPAIR_RULE_IDS.size).toBe(13);expect(PAPER_LINT_REPAIR_RULE_IDS.has('sjtu_rule_24')).toBe(true);
 expect(PAPER_LINT_REPAIR_RULE_IDS.has('sjtu_rule_2')).toBe(false);
});
