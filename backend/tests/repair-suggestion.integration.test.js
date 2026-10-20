import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const {
  buildArchiveRepairRequest,
  findRepairSuggestion,
  listArchiveRepairSuggestions,
  saveRepairSuggestion,
} = require('../src/normative/repairSuggestionService');

const harness = createTestDatabaseHarness({ label: 'repair-suggestion' });
let db;

function report() {
  return {
    execution_provenance: { pdf_sha: 'a'.repeat(64), detector_version_sha: 'detector-v1' },
    rule_runs: [{ rule_id: 'sjtu_rule_15', findings: [{
      finding_id: 'sjtu_rule_15_1', message: '图 2.3 未被全文引用', anchors: [
        { location: { page_number: 8, text_excerpt: '本章实验流程说明。' } },
      ],
      location: { type: 'pdf_bbox', page_number: 12, text_excerpt: '图 2.3 实验流程', bounding_rect: { page_number: 12 } },
    }] }],
  };
}

beforeEach(async () => {
  db = await harness.setup();
  await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('admin', 'admin', 'hash', 'SCHOOL_ADMIN', 'SCHOOL')");
  await db.run("INSERT INTO archive_scan_jobs (id, created_by, selected_rule_ids_json, status, total_count) VALUES ('job-1', 'admin', '[\"sjtu_rule_15\"]', 'completed', 1)");
  await db.run(
    "INSERT INTO archive_scan_documents (id, job_id, relative_path, filename, size_bytes, status, result_json) VALUES ('doc-1', 'job-1', 'paper.pdf', 'paper.pdf', 1, 'completed', ?)",
    [JSON.stringify(report())],
  );
});
afterEach(async () => { await harness.cleanup(); });

describe('archive repair suggestion interfaces', () => {
  it('builds an evidence-bound request from a persisted archive finding', async () => {
    const input = { jobId: 'job-1', documentId: 'doc-1', ruleId: 'sjtu_rule_15', findingId: 'sjtu_rule_15_1' };
    const request = await buildArchiveRepairRequest(input);
    expect(request.schema_version).toBe('repair-request-v1');
    expect(request.source.document_sha256).toBe('a'.repeat(64));
    expect(request.evidence).toEqual([
      expect.objectContaining({ evidence_id: 'legacy-evidence-1', page_number: 12 }),
      expect.objectContaining({ evidence_id: 'legacy-evidence-2', page_number: 8, source_kind: 'retrieval' }),
    ]);
    expect(request.context_sha256).toHaveLength(64);
    expect(await listArchiveRepairSuggestions(input)).toEqual([]);
  });

  it('caches a response by evidence context, model, model version and prompt version', async () => {
    const input = { jobId: 'job-1', documentId: 'doc-1', ruleId: 'sjtu_rule_15', findingId: 'sjtu_rule_15_1' };
    const request = await buildArchiveRepairRequest(input);
    const response = {
      schema_version: 'repair-response-v1', source: request.source, rule_id: input.ruleId, finding_id: input.findingId,
      status: 'suggested', suggestion: '补充正文引用。', rationale: '图题已定位。',
      actions: [], missing_context: [], evidence_ids: ['legacy-evidence-1'],
      provenance: {
        provider: 'huawei_maas', model: 'test-model', model_version: 'model-v1',
        prompt_version: 'prompt-v1', context_sha256: request.context_sha256, generated_at: '2026-10-19T00:00:00.000Z',
      },
      usage: { input_tokens: 1, output_tokens: 1, attempts: 1 },
    };
    const savedResponse = await saveRepairSuggestion(request, response);
    expect(await findRepairSuggestion(request, {
      model: 'test-model', modelVersion: 'model-v1', promptVersion: 'prompt-v1',
    })).toEqual(savedResponse);
    expect(await findRepairSuggestion(request, {
      model: 'test-model', modelVersion: 'model-v2', promptVersion: 'prompt-v1',
    })).toBeNull();
  });
});
