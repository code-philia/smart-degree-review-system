import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { appendExtractedContext } = require('../src/normative/repairEvidenceService');

function request() {
  return {
    rule: { rule_id: 'sjtu_rule_15' },
    finding: { finding_id: 'finding-1', message: '图 2.3 未被全文引用' },
    evidence: [{ evidence_id: 'legacy-evidence-1', source_kind: 'pdf_text', text: '图 2.3', page_number: 31, source_ref: 'finding' }],
    context_sha256: 'old',
  };
}

describe('adaptive PDF repair context', () => {
  it('preserves each extracted page as separately traceable evidence', () => {
    const result = appendExtractedContext(request(), {
      segments: [
        { page_number: 30, relation: 'before', text: '第 30 页相关正文。' },
        { page_number: 31, relation: 'target', text: '第 31 页图题。' },
        { page_number: 32, relation: 'after', text: '第 32 页后续正文。' },
      ],
    }, { page_number: 31 }, 'legacy_archive:pdf_context:paper.pdf');

    expect(result.evidence).toEqual([
      expect.objectContaining({ evidence_id: 'legacy-evidence-1' }),
      expect.objectContaining({ evidence_id: 'pdf-context-2', page_number: 30, source_ref: 'legacy_archive:pdf_context:paper.pdf#page=30&relation=before' }),
      expect.objectContaining({ evidence_id: 'pdf-context-3', page_number: 31, source_ref: 'legacy_archive:pdf_context:paper.pdf#page=31&relation=target' }),
      expect.objectContaining({ evidence_id: 'pdf-context-4', page_number: 32, source_ref: 'legacy_archive:pdf_context:paper.pdf#page=32&relation=after' }),
    ]);
    expect(result.context_sha256).not.toBe('old');
  });
});
