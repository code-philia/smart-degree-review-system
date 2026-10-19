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
        status: 'suggested', actions: [{ instruction: '在正文加入引用。', evidence_ids: ['e1'] }],
      }) } }], usage: { prompt_tokens: 20, completion_tokens: 10 },
    }), { status: 200 });
    const response = await proposeRepair(request, { fetchImpl });
    expect(response.status).toBe('suggested');
    expect(response.schema_version).toBe('repair-response-v2');
    expect(response.usage).toEqual({ input_tokens: 20, output_tokens: 10, attempts: 1 });
    expect(response.provenance.context_sha256).toBe(request.context_sha256);
  });

  it('rejects evidence ids not supplied to the model', () => {
    expect(() => validateModelAnswer({
      status: 'suggested', actions: [{ instruction: '建议。', evidence_ids: ['missing'] }],
    }, request)).toThrow(/不存在的证据/);
  });

  it('instructs the model to make safe conditional suggestions before declaring context insufficient', () => {
    expect(buildMessages(request)[0].content).toContain('以修改为中心');
    expect(buildMessages(request)[0].content).toContain('控制建议数量');
  });
});
