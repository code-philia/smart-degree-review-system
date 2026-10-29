const ALLOWED_STATUSES = new Set(['suggested', 'insufficient_context', 'evidence_conflict']);
const PROMPT_VERSION = 'repair-model-actions-v6';
const MAX_EVIDENCE_ITEMS = 8;
const MAX_EVIDENCE_CHARS = 12000;

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function modelConfig() {
  const apiKey = process.env.SJTU_API_KEY;
  const baseUrl = process.env.SJTU_API_BASE_URL;
  const model = process.env.SJTU_API_MODEL;
  if (!apiKey || !baseUrl || !model) {
    throw problem(503, '修复建议模型未配置：需要校内 SJTU_API_* 配置');
  }
  return { apiKey, baseUrl: baseUrl.replace(/\/$/, ''), model,
    modelVersion: process.env.SJTU_API_MODEL_VERSION || 'campus-current',
    provider: 'sjtu' };
}

function boundedCitationText(value, limit) {
  const text = String(value || '');
  if (text.length <= limit) return text;
  const marker = text.search(/\n来源(?:标识|链接)：/);
  if (marker < 0) return text.slice(0, limit);
  const provenance = text.slice(marker);
  if (provenance.length >= limit) return provenance.slice(0, limit);
  const separator = '\n…';
  const quoteLength = Math.max(0, limit - provenance.length - separator.length);
  return (text.slice(0, quoteLength) + separator + provenance).slice(-limit);
}

function boundedEvidence(evidence, ruleId) {
  let total = 0;
  const result = [];
  const isContext = item => String(item.source_ref || '').includes('pdf_context');
  const contexts = evidence.filter(isContext);
  const primary = evidence.filter(item => !isContext(item));
  const citation = ['sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33'].includes(ruleId);
  let ordered;
  let criticalCount = 0;
  if (citation) {
    const priority = item => {
      const ref = String(item.source_ref || '');
      if (ref.includes('finding_location')) return 0;
      if (ref.startsWith('paper_compiler:normative')) return 1;
      if (ref.startsWith('paper_compiler:controlled_catalog_scope:')) return 2;
      return 3;
    };
    // Reserve evidence slots and characters for cited content, scope proofs and
    // normative excerpts; neighboring pages use the remaining optional budget.
    const critical = [...primary].sort((a, b) => priority(a) - priority(b));
    criticalCount = Math.min(critical.length, MAX_EVIDENCE_ITEMS);
    contexts.sort((a, b) => Number(String(b.source_ref).includes('relation=target')) - Number(String(a.source_ref).includes('relation=target')));
    ordered = [...critical, ...contexts];
  } else {
    ordered = [...contexts, ...primary];
  }
  for (const [index, item] of ordered.slice(0, MAX_EVIDENCE_ITEMS).entries()) {
    const remaining = MAX_EVIDENCE_CHARS - total;
    if (remaining <= 0) break;
    const criticalRemaining = citation ? Math.max(0, criticalCount - index) : 0;
    const limit = criticalRemaining ? Math.floor(remaining / criticalRemaining) : remaining;
    const text = citation ? boundedCitationText(item.text, limit) : String(item.text || '').slice(0, limit);
    total += text.length;
    result.push({ evidence_id: item.evidence_id, source_kind: item.source_kind, page_number: item.page_number, text });
  }
  return result;
}

function buildMessages(request) {
  const evidence = boundedEvidence(request.evidence, request.rule.rule_id);
  const bilingual = ['bilingual_abstract_consistency_check', 'bilingual_keywords_correspondence_check']
    .includes(request.rule.rule_id);
  const typo = request.rule.rule_id === 'typo_detection_check';
  const typoInstructions = typo ? `
## 错别字规则专用要求
只处理证据中能够在 PDF 原文定位到的明确错别字。必须保留原文短语的准确字面，并在 instruction 中使用“修改前：……；修改后：……”明确标注；不要把跨行连字符、中文字符间的 PDF 提取空格、专业术语或专有名词当成错误。无法确认时返回 insufficient_context，不要强行改写。` : '';
  const bilingualInstructions = bilingual ? `
## 中英文双语规则专用要求
这是中英文摘要/关键词对应规则。输入证据中的“中文原文”和“英文原文”是本次判断的核心上下文，不能把它们当成泛泛的摘要信息。
如果状态为 suggested，建议必须同时引用中文和英文原文证据，但必须保持保守：不得仅凭摘要或关键词擅自认定中文或英文哪一侧正确，不得输出“以中文为准”“以英文为准”“将英文改成中文”等绝对结论。英文关键词中字母之间的单个连字符可能来自 PDF 跨行换行；没有明确原文证据时，不得建议删除或改写该连字符。应明确指出两侧的具体差异，建议作者结合正文、方法、实验结果和术语定义核对后再决定修改哪一侧；除非输入证据明确证明某一侧是权威版本，否则只提出同步核对和最小修改方向。
如果状态为 insufficient_context，只能明确指出缺少哪一侧的哪一段原文（包括页码或定位）；如果输入已经有两侧原文，不得再笼统要求“提供摘要信息”或“核对摘要”。
` : '';
  const expected = {
    status: 'suggested | insufficient_context | evidence_conflict',
    actions: [{ instruction: 'string', evidence_ids: ['evidence id'] }],
    missing_context: ['string'],
  };
  return [
    {
      role: 'system',
      content: `你是学位论文规范问题的修复建议助手。请根据规则、告警和证据，为论文作者提供简明、具体、可直接执行的修复建议。
所有面向用户的 summary、instruction、missing_context 必须使用简体中文；原文证据和英文术语可保持原样。

## 修复原则（按优先级执行）

1. **证据可靠**：仅依据输入信息判断，可进行合理推断，但不得编造公式、图表、编号、数据或引用关系。不能仅因对象位置相邻或内容相似，就认定其为正确的替换目标。
2. **最小修复**：优先选择能消除告警、保持原意且引入最少额外假设的修改方式。可采用删除、替换、补充或调整措辞，不必强行寻找替换对象。
3. **主动建议**：有合理修复方案时直接给出具体操作，避免将判断过程交给用户；只有无法确定合理修改方式时才要求核对。
4. **精准简洁**：尽量包含页码、原文短片段及明确修改动作，优先使用“在第X页‘原文片段’处，将A修改为B”。原文片段必须来自输入证据，不得改写或补造。每条建议原则上为1～2句话，不输出排查流程。
5. **定位准确**：使用原文上下文作为定位锚点：如果输入证据包含问题原文及其前后文，应优先提取能够唯一识别修改位置的连续原文片段。片段应包含待修改内容，并尽量保留其前后各约 10～20 个汉字。不得改写、补造或拼接不存在的原文。若原文较长，只截取与修改直接相关的部分。

${bilingualInstructions}${typoInstructions}
## 状态规则

- suggested：现有证据支持合理的具体修复方案，包括必要的合理推断。
- insufficient_context：无法提出有依据的修复方案；actions 应说明最关键的待核对信息。
- evidence_conflict：现有证据直接反驳原告警，或明显表明原告警不成立。

## 输出要求

仅输出一个符合以下结构的 JSON 对象，不要 Markdown。
每步 evidence_ids 只能引用输入中已有的证据 ID。
同一修改目标尽量合并为一条建议，只有独立修改目标才拆分。
不要输出内部推理过程或无必要的复核步骤。

JSON 结构：${JSON.stringify(expected)}`,
    },
    {
      role: 'user',
      content: JSON.stringify({
        rule: request.rule,
        finding: {
          finding_id: request.finding.finding_id,
          message: request.finding.message,
          location: request.finding.location || null,
          anchors: Array.isArray(request.finding.anchors) ? request.finding.anchors : [],
        },
        evidence,
      }),
    },
  ];
}

function parseJson(content) {
  if (typeof content !== 'string') throw problem(502, '修复建议模型返回为空');
  const trimmed = content.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  try { return JSON.parse(trimmed); } catch {
    const start = trimmed.indexOf('{');
    if (start < 0) throw problem(502, '修复建议模型返回了无法解析的 JSON');
    try {
      const value = JSON.parse(trimmed.slice(start));
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('not object');
      return value;
    } catch { throw problem(502, '修复建议模型返回了无法解析的 JSON'); }
  }
}

function validateModelAnswer(answer, request) {
  if (!answer || !ALLOWED_STATUSES.has(answer.status)) throw problem(502, '修复建议模型返回了无效状态');
  const validIds = new Set(boundedEvidence(request.evidence, request.rule.rule_id).map((item) => item.evidence_id));
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
  const missingContext = Array.isArray(answer.missing_context)
    ? answer.missing_context.filter((item) => typeof item === 'string' && item.trim()).map((item) => item.trim()).slice(0, 8)
    : [];
  const bilingual = ['bilingual_abstract_consistency_check', 'bilingual_keywords_correspondence_check']
    .includes(request.rule.rule_id);
  const typo = request.rule.rule_id === 'typo_detection_check';
  const typoInstructions = typo ? `
## 错别字规则专用要求
只处理证据中能够在 PDF 原文定位到的明确错别字。必须保留原文短语的准确字面，并在 instruction 中使用“修改前：……；修改后：……”明确标注；不要把跨行连字符、中文字符间的 PDF 提取空格、专业术语或专有名词当成错误。无法确认时返回 insufficient_context，不要强行改写。` : '';
  if (bilingual && answer.status === 'suggested') {
    const bilingualIds = validIds.has('bilingual-evidence-1') && validIds.has('bilingual-evidence-2')
      ? ['bilingual-evidence-1', 'bilingual-evidence-2'] : [];
    const citedBilingualIds = new Set(actions.flatMap((action) => action.evidence_ids));
    if (bilingualIds.length === 2 && !bilingualIds.every((id) => citedBilingualIds.has(id))) {
      throw problem(502, '双语修复建议必须引用中文和英文原文证据');
    }
  }
  return {
    status: answer.status,
    actions,
    ...(missingContext.length ? { missing_context: missingContext } : {}),
  };
}

function runMeteredRepair(messages, info = false) {
  const { execFile } = require('child_process');
  const path = require('path');
  const python = process.env.REPAIR_MODEL_PYTHON || process.env.SIX_RULE_PYTHON || 'python3';
  const script = path.resolve(__dirname, '../../scripts/repair_model_proposal.py');
  return new Promise((resolve, reject) => {
    const child = execFile(python, [script, ...(info ? ['--info'] : [])], {
      timeout: 125000, maxBuffer: 1024 * 1024, encoding: 'utf8',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' },
    }, (error, stdout) => {
      let output;
      try { output = JSON.parse(stdout); } catch {
        reject(problem(error?.killed ? 504 : 503, error?.killed ? '修复建议模型请求超时' : '修复建议模型暂不可用'));
        return;
      }
      if (output.status === 'error') reject(problem(output.http_status || 502, output.message || '修复建议生成失败'));
      else if (error) reject(problem(502, '修复建议生成失败'));
      else resolve(output);
    });
    child.stdin.on('error', () => {});
    child.stdin.end(info ? '' : JSON.stringify({ messages }));
  });
}

async function getRepairModelIdentity() {
  return runMeteredRepair(null, true);
}

function repairResponse(request, answer, config, usage) {
  return {
    schema_version: 'repair-response-v2', source: request.source,
    rule_id: request.rule.rule_id, finding_id: request.finding.finding_id,
    ...answer,
    provenance: {
      provider: config.provider || 'sjtu', model: config.model, model_version: config.modelVersion,
      prompt_version: PROMPT_VERSION, context_sha256: request.context_sha256,
      source_identity_sha256: request.source_identity_sha256,
      generated_at: new Date().toISOString(),
    },
    usage,
  };
}

async function proposeRepair(request, { fetchImpl } = {}) {
  if (!fetchImpl) {
    const output = await runMeteredRepair(buildMessages(request));
    return repairResponse(request, validateModelAnswer(output.answer, request), output, output.usage);
  }
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
  return repairResponse(request, answer, config, {
    input_tokens: Number(payload?.usage?.prompt_tokens) || 0,
    output_tokens: Number(payload?.usage?.completion_tokens) || 0, attempts: 1,
  });
}

module.exports = { PROMPT_VERSION, buildMessages, proposeRepair, validateModelAnswer, getRepairModelIdentity };
