const ALLOWED_STATUSES = new Set(['suggested', 'insufficient_context', 'evidence_conflict']);
const PROMPT_VERSION = 'repair-model-actions-v2';
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
    actions: [{ instruction: 'string', evidence_ids: ['evidence id'] }],
  };
  return [
    {
      role: 'system',
      content: `你是学位论文规范问题的修复建议助手。你的任务是根据规则、告警和证据，为论文作者提供简明、准确、可执行的修复建议。

## 基本约束

- 只能依据提供的规则、告警和证据作答。
- 不得补造图表、公式、数据、参考文献、作者或实验事实。
- 不得将未经证实的推测表述为确定事实。
- 每步 evidence_ids 只能引用输入中已有的证据 ID。

## 修复建议生成原则

1. **以修改为中心**：直接说明需要修改的位置、对象和方式，而不是描述完整的排查过程。
2. **简洁优先**：每条建议原则上为 1～2 句话，避免重复告警内容、冗长解释和无必要的技术细节。
3. **合并相关操作**：针对同一修改目标的定位、核对和修改应尽量合并为一条建议，不得为了体现完整性而拆分步骤。
4. **保留必要条件**：如果修改目标不唯一，使用简短的“若……则……”说明不同处理方式，不必穷举缺乏证据支持的可能性。
5. **突出用户行动**：优先使用“将……修改为……”“补充……”“删除……”“核对……后调整……”等表达。
6. **避免流程化表述**：除非必要，不输出全文检索、记录上下文、重新编译、检查编号连续性等辅助操作。
7. **控制建议数量**：能够通过一条建议完整表达的，不拆分为多条；只有涉及独立修改目标时才分别给出。

输出一个 JSON 对象，不要 markdown。状态仅可为 suggested、insufficient_context、evidence_conflict。若证据不足，actions 应写明下一步需要补取或核对什么；只有补取证据直接反驳或明显不支持原告警时，使用 evidence_conflict。JSON 结构：${JSON.stringify(expected)}`,
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
  if (!Array.isArray(answer.actions) || answer.actions.length === 0) {
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
    actions,
  };
}

async function proposeRepair(request, { fetchImpl = fetch } = {}) {
  const config = modelConfig();
  const controller = new AbortController();
  let timeout;
  let payload;
  try {
    // Aborting the request alone is not sufficient if a provider has sent
    // headers but then stalls while streaming the response body. Race the
    // entire fetch-and-parse operation against an explicit rejection so a
    // batch worker cannot wait forever on one finding.
    payload = await new Promise((resolve, reject) => {
      timeout = setTimeout(() => {
        controller.abort();
        reject(problem(504, '修复建议模型请求超时'));
      }, 30000);
      fetchImpl(`${config.baseUrl}/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.apiKey}` },
        body: JSON.stringify({ model: config.model, temperature: 0.1, messages: buildMessages(request) }),
        signal: controller.signal,
      }).then(async (response) => {
        if (!response.ok) throw problem(response.status >= 500 ? 502 : 424, `修复建议模型请求失败（HTTP ${response.status}）`);
        return response.json();
      }).then(resolve, reject);
    });
  } catch (error) {
    if (error.status) throw error;
    throw problem(error.name === 'AbortError' ? 504 : 502, error.name === 'AbortError' ? '修复建议模型请求超时' : '修复建议模型请求失败');
  } finally {
    clearTimeout(timeout);
  }
  const answer = validateModelAnswer(parseJson(payload?.choices?.[0]?.message?.content), request);
  return {
    schema_version: 'repair-response-v2', source: request.source,
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
