const ALLOWED_STATUSES = new Set(['suggested', 'insufficient_context', 'evidence_conflict']);
const PROMPT_VERSION = 'repair-model-initial-v2';
const MAX_EVIDENCE_ITEMS = 8;
const MAX_EVIDENCE_CHARS = 12000;

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function modelConfig() {
  const apiKey = process.env.MAAS_API_KEY;
  const baseUrl = process.env.MAAS_BASE_URL;
  const model = process.env.MAAS_MODEL;
  if (!apiKey || !baseUrl || !model) {
    throw problem(503, '修复建议模型未配置：需要 MAAS_API_KEY、MAAS_BASE_URL 和 MAAS_MODEL');
  }
  return { apiKey, baseUrl: baseUrl.replace(/\/$/, ''), model, modelVersion: process.env.MAAS_MODEL_VERSION || 'unknown' };
}

function boundedEvidence(evidence) {
  let total = 0;
  const result = [];
  for (const item of evidence.slice(0, MAX_EVIDENCE_ITEMS)) {
    const remaining = MAX_EVIDENCE_CHARS - total;
    if (remaining <= 0) break;
    const text = String(item.text || '').slice(0, remaining);
    total += text.length;
    result.push({ evidence_id: item.evidence_id, source_kind: item.source_kind, page_number: item.page_number, text });
  }
  return result;
}

function buildMessages(request) {
  const evidence = boundedEvidence(request.evidence);
  const expected = {
    status: 'suggested | insufficient_context | evidence_conflict',
    suggestion: 'string',
    rationale: 'string',
    actions: [{ instruction: 'string', evidence_ids: ['evidence id'] }],
    missing_context: ['string'],
    evidence_ids: ['evidence id'],
  };
  return [
    {
      role: 'system',
      content: `你是学位论文规范问题的修复建议助手。只可依据提供的规则、告警和证据作答；不得补造图表、公式、数据、参考文献、作者或实验事实。输出一个 JSON 对象，不要 markdown。状态仅可为 suggested、insufficient_context、evidence_conflict。若能提出不虚构、可验证的操作步骤，即使候选修改目标不唯一，也应使用 suggested，并明确写出“若…则…”的条件和需要核对的位置。仅当无法提出安全且有用的操作步骤时，才使用 insufficient_context；图表内容不可见本身不构成 insufficient_context，除非无法说明应核对什么。只有补取证据直接反驳或明显不支持原告警时，使用 evidence_conflict。actions 和 evidence_ids 只能引用输入中给出的 evidence_id。JSON 结构：${JSON.stringify(expected)}`,
    },
    {
      role: 'user',
      content: JSON.stringify({
        rule: request.rule,
        finding: { finding_id: request.finding.finding_id, message: request.finding.message },
        evidence,
      }),
    },
  ];
}

function parseJson(content) {
  if (typeof content !== 'string') throw problem(502, '修复建议模型返回为空');
  const trimmed = content.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  try { return JSON.parse(trimmed); } catch { throw problem(502, '修复建议模型返回了无法解析的 JSON'); }
}

function validateModelAnswer(answer, request) {
  if (!answer || !ALLOWED_STATUSES.has(answer.status)) throw problem(502, '修复建议模型返回了无效状态');
  const validIds = new Set(request.evidence.map((item) => item.evidence_id));
  const normalizeIds = (ids) => {
    if (!Array.isArray(ids) || ids.some((id) => typeof id !== 'string' || !validIds.has(id))) {
      throw problem(502, '修复建议模型引用了不存在的证据');
    }
    return [...new Set(ids)];
  };
  if (typeof answer.suggestion !== 'string' || !answer.suggestion.trim() || typeof answer.rationale !== 'string' || !answer.rationale.trim()) {
    throw problem(502, '修复建议模型缺少建议或依据');
  }
  if (!Array.isArray(answer.actions) || !Array.isArray(answer.missing_context)) {
    throw problem(502, '修复建议模型返回了无效操作步骤');
  }
  const actions = answer.actions.map((action) => {
    if (!action || typeof action.instruction !== 'string' || !action.instruction.trim()) {
      throw problem(502, '修复建议模型返回了无效操作步骤');
    }
    return { instruction: action.instruction.trim(), evidence_ids: normalizeIds(action.evidence_ids) };
  });
  return {
    status: answer.status,
    suggestion: answer.suggestion.trim(),
    rationale: answer.rationale.trim(),
    actions,
    missing_context: answer.missing_context.filter((item) => typeof item === 'string' && item.trim()).map((item) => item.trim()),
    evidence_ids: normalizeIds(answer.evidence_ids),
  };
}

async function proposeRepair(request, { fetchImpl = fetch } = {}) {
  const config = modelConfig();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  let payload;
  try {
    const response = await fetchImpl(`${config.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.apiKey}` },
      body: JSON.stringify({ model: config.model, temperature: 0.1, messages: buildMessages(request) }),
      signal: controller.signal,
    });
    if (!response.ok) throw problem(response.status >= 500 ? 502 : 424, `修复建议模型请求失败（HTTP ${response.status}）`);
    payload = await response.json();
  } catch (error) {
    if (error.status) throw error;
    throw problem(error.name === 'AbortError' ? 504 : 502, error.name === 'AbortError' ? '修复建议模型请求超时' : '修复建议模型请求失败');
  } finally {
    clearTimeout(timeout);
  }
  const answer = validateModelAnswer(parseJson(payload?.choices?.[0]?.message?.content), request);
  return {
    schema_version: 'repair-response-v1', source: request.source,
    rule_id: request.rule.rule_id, finding_id: request.finding.finding_id,
    ...answer,
    provenance: {
      provider: 'huawei_maas', model: config.model, model_version: config.modelVersion,
      prompt_version: PROMPT_VERSION, context_sha256: request.context_sha256, generated_at: new Date().toISOString(),
    },
    usage: {
      input_tokens: Number(payload?.usage?.prompt_tokens) || 0,
      output_tokens: Number(payload?.usage?.completion_tokens) || 0,
      attempts: 1,
    },
  };
}

module.exports = { PROMPT_VERSION, buildMessages, proposeRepair, validateModelAnswer };
