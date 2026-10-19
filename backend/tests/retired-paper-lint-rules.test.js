import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const service = require('../src/normative/reviewPilotPaperLintService');
const itWithEngine = fs.existsSync(path.join(service.resolveEngineBackendDir(), 'novref/domain/paper_lint')) ? it : it.skip;
const retiredIds = ['claim_evidence_inconsistency_check', 'strong_claim_without_evidence_check'];

describe('retired normative checks', () => {
  itWithEngine('omits the retired checks from the real engine catalog and retains bilingual and citation checks', async () => {
    const catalog = await service.getPaperLintCatalog({ refresh: true });
    expect(catalog.engine).toBe('review-pilot');
    const ids = catalog.rules.map(rule => rule.rule_id);
    for (const id of retiredIds) expect(ids).not.toContain(id);
    expect(ids).toEqual(expect.arrayContaining([
      'bilingual_abstract_consistency_check', 'sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33',
    ]));
  }, 40000);

  it.each(retiredIds)('rejects a stale catalog request for %s', (ruleId) => {
    const staleCatalog = { rules: [{ rule_id: ruleId, title: '旧规则', available: true }] };
    expect(() => service.validateSelectedRuleIds(staleCatalog, [ruleId])).toThrow(/已下线/);
  });
});
