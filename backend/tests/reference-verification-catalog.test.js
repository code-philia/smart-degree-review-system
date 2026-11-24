import { expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const registry=require('../rules/registry');
const service=require('../src/normative/reviewPilotPaperLintService');
it('exposes the new database check independently and keeps old reference checks retired',async()=>{
  const ids=registry.getEnabledMvpRuleIds();
  expect(ids).toContain('reference_verification_check');expect(ids).not.toContain('sjtu_rule_32');
  const catalog=await service.getPaperLintCatalog({refresh:true});
  expect(catalog.rules.find(r=>r.rule_id==='reference_verification_check')).toMatchObject({uses_external_model:false,repair_supported:false,execution_mode:'deterministic',default_enabled:false,default_selected:false});
  expect(service.validateSelectedRuleIds(catalog,['reference_verification_check'])).toEqual(['reference_verification_check']);
  expect(()=>service.validateSelectedRuleIds(catalog,['sjtu_rule_32'])).toThrow(/已下线/);
});
it('preserves the new result in the same projection that hides retired historical results',async()=>{
  const {visiblePaperLintResult}=await import('../../shared/paper-lint-presentation.mjs');
  const current={rule_id:'reference_verification_check',execution_status:'completed',findings:[{message:'new',severity:'info'}]};
  expect(visiblePaperLintResult({rule_runs:[{rule_id:'sjtu_rule_32',findings:[{message:'old'}]},current]}).rule_runs).toEqual([current]);
});
