import { describe, expect, it, afterEach } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { buildMessages, proposeRepair, validateModelAnswer } = require('../src/normative/repairModelProposalService');

const saved = { ...process.env };
afterEach(() => {
  for (const key of ['MAAS_API_KEY', 'MAAS_BASE_URL', 'MAAS_MODEL', 'MAAS_MODEL_VERSION']) {
    if (saved[key] === undefined) delete process.env[key]; else process.env[key] = saved[key];
  }
});

const request = {
  source: { kind: 'legacy_archive', job_id: 'job', document_id: 'doc', document_sha256: 'a'.repeat(64), detector_version: 'v1' },
  rule: { rule_id: 'sjtu_rule_15', text: '出现未被引用的图。', version: 'v1' },
  finding: { finding_id: 'finding', message: '图 2.3 未被全文引用' },
  context_sha256: 'b'.repeat(64),
  evidence: [{ evidence_id: 'e1', source_kind: 'pdf_text', text: '图 2.3 实验流程', page_number: 12, source_ref: 'test' }],
};

describe('repair model proposal', () => {
  it('returns a structured response from a valid single-model result', async () => {
    process.env.MAAS_API_KEY = 'test-key'; process.env.MAAS_BASE_URL = 'https://example.test/v1';
    process.env.MAAS_MODEL = 'test-model'; process.env.MAAS_MODEL_VERSION = 'test-version';
    const fetchImpl = async () => new Response(JSON.stringify({
      choices: [{ message: { content: JSON.stringify({
        status: 'suggested', suggestion: '补充图 2.3 的正文引用。', rationale: '图题已定位。',
        actions: [{ instruction: '在正文加入引用。', evidence_ids: ['e1'] }], missing_context: [], evidence_ids: ['e1'],
      }) } }], usage: { prompt_tokens: 20, completion_tokens: 10 },
    }), { status: 200 });
    const response = await proposeRepair(request, { fetchImpl });
    expect(response.status).toBe('suggested');
    expect(response.usage).toEqual({ input_tokens: 20, output_tokens: 10, attempts: 1 });
    expect(response.provenance.context_sha256).toBe(request.context_sha256);
  });

  it('rejects evidence ids not supplied to the model', () => {
    expect(() => validateModelAnswer({
      status: 'suggested', suggestion: '建议。', rationale: '依据。', actions: [], missing_context: [], evidence_ids: ['missing'],
    }, request)).toThrow(/不存在的证据/);
  });

  it('instructs the model to make safe conditional suggestions before declaring context insufficient', () => {
    expect(buildMessages(request)[0].content).toContain('即使候选修改目标不唯一，也应使用 suggested');
    expect(buildMessages(request)[0].content).toContain('无法提出安全且有用的操作步骤');
  });
});
