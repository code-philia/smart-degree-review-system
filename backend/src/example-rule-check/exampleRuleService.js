const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const repository = require("./exampleRuleRepository");
const MAX_PDF_BYTES = 50 * 1024 * 1024,
  MAX_TEXT_CHARS = 120000,
  MAX_RULES_PER_RUN = 5,
  MAX_ANNOTATIONS = 80,
  TIMEOUT_MS = 45000;
let inFlight = 0;
const MAX_CONCURRENCY = 2;
const error = (status, message) =>
  Object.assign(new Error(message), { status });
function validatePdf(buffer) {
  if (
    !Buffer.isBuffer(buffer) ||
    buffer.length < 5 ||
    buffer.length > MAX_PDF_BYTES ||
    buffer.subarray(0, 5).toString("ascii") !== "%PDF-"
  )
    throw error(400, "请上传不超过 50 MB 的有效 PDF 文件");
}
function validateAnnotations(value) {
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    value.length > MAX_ANNOTATIONS
  )
    throw error(400, "请至少添加一条、且不超过 80 条示例标注");
  return value.map((item, index) => {
    if (
      !item ||
      !["focus", "pass", "fail", "exception", "note"].includes(item.type) ||
      !Number.isInteger(item.page_number) ||
      item.page_number < 1 ||
      typeof item.text_excerpt !== "string" ||
      item.text_excerpt.trim().length < 2
    )
      throw error(
        400,
        `第 ${index + 1} 条标注不完整：需要类型、页码和至少 2 个字符的摘录`,
      );
    return {
      type: item.type,
      block_type: ["text", "figure", "table", "equation"].includes(
        item.block_type,
      )
        ? item.block_type
        : "text",
      page_number: item.page_number,
      text_excerpt: item.text_excerpt.trim().slice(0, 2000),
      note:
        typeof item.note === "string" ? item.note.trim().slice(0, 1000) : "",
      bounding_rect: item.bounding_rect || null,
    };
  });
}
function validateDefinition(value) {
  if (
    !value ||
    typeof value !== "object" ||
    typeof value.title !== "string" ||
    !value.title.trim() ||
    typeof value.check_description !== "string" ||
    !value.check_description.trim() ||
    !Array.isArray(value.criteria) ||
    value.criteria.length === 0
  )
    throw error(400, "规则定义缺少标题、检查说明或判定条件");
  return {
    title: value.title.trim().slice(0, 120),
    check_description: value.check_description.trim().slice(0, 3000),
    criteria: value.criteria
      .slice(0, 12)
      .map((x) => String(x).trim())
      .filter(Boolean),
    exception_notes: Array.isArray(value.exception_notes)
      ? value.exception_notes.slice(0, 12).map(String)
      : [],
    suggestion_template:
      typeof value.suggestion_template === "string"
        ? value.suggestion_template.trim().slice(0, 1000)
        : "",
  };
}
function validateRuleInput(body) {
  if (
    !body ||
    typeof body.name !== "string" ||
    !body.name.trim() ||
    typeof body.intent !== "string" ||
    !body.intent.trim()
  )
    throw error(400, "请填写规则名称和希望检查什么");
  if (!["enabled", "disabled"].includes(body.status))
    throw error(400, "规则启停状态无效");
  return {
    name: body.name.trim().slice(0, 120),
    intent: body.intent.trim().slice(0, 3000),
    status: body.status,
    definition: validateDefinition(body.definition),
  };
}
function validateModelRule(value) {
  return validateDefinition(value);
}
function validateModelResult(value) {
  if (!value || !Array.isArray(value.rule_results))
    throw error(502, "DeepSeek 返回的检测结果结构无效");
  return value.rule_results.slice(0, MAX_RULES_PER_RUN).map((x, i) => {
    if (
      !x ||
      typeof x.rule_id !== "string" ||
      !["pass", "issue", "not_applicable", "undetermined"].includes(
        x.outcome,
      ) ||
      !Array.isArray(x.evidence)
    )
      throw error(502, `DeepSeek 返回的第 ${i + 1} 条结果结构无效`);
    return {
      rule_id: x.rule_id,
      outcome: x.outcome,
      conclusion: String(x.conclusion || "").slice(0, 2000),
      suggestion: String(x.suggestion || "").slice(0, 2000),
      evidence: x.evidence
        .slice(0, 8)
        .map((e) => ({
          page_number: Number.isInteger(e.page_number) ? e.page_number : 1,
          text_excerpt: String(e.text_excerpt || "").slice(0, 2000),
          bounding_rect: e.bounding_rect || null,
        })),
    };
  });
}
async function extractText(buffer) {
  const dir = await fs.promises.mkdtemp(
    path.join(os.tmpdir(), "example-rule-"),
  );
  const file = path.join(dir, "source.pdf");
  try {
    await fs.promises.writeFile(file, buffer, { mode: 0o600 });
    const text = await new Promise((resolve, reject) => {
      const child = spawn("pdftotext", ["-enc", "UTF-8", file, "-"], {
        stdio: ["ignore", "pipe", "pipe"],
      });
      let out = "",
        err = "";
      const timer = setTimeout(() => child.kill("SIGKILL"), 15000);
      child.stdout.on("data", (d) => (out += d));
      child.stderr.on("data", (d) => (err += d));
      child.on("error", reject);
      child.on("close", (code) => {
        clearTimeout(timer);
        code === 0
          ? resolve(out)
          : reject(
              error(
                400,
                err.includes("Encrypted")
                  ? "暂不支持加密或需要密码的 PDF"
                  : "PDF 解析失败，请确认文件可读取",
              ),
            );
      });
    });
    if (!text.trim())
      throw error(400, "未从 PDF 提取到文字，该文件可能是扫描件或缺少文字层");
    return text.replace(/\s+/g, " ").trim().slice(0, MAX_TEXT_CHARS);
  } finally {
    await fs.promises.rm(dir, { recursive: true, force: true });
  }
}
async function modelJson(system, user) {
  if (!process.env.DEEPSEEK_API_KEY)
    throw error(503, "服务器尚未配置 DeepSeek，暂不能执行此操作");
  if (inFlight >= MAX_CONCURRENCY)
    throw error(429, "当前模型请求较多，请稍后重试");
  inFlight++;
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch("https://api.deepseek.com/chat/completions", {
      method: "POST",
      signal: controller.signal,
      headers: {
        authorization: `Bearer ${process.env.DEEPSEEK_API_KEY}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: process.env.DEEPSEEK_MODEL || "deepseek-chat",
        temperature: 0.1,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
      }),
    });
    if (!response.ok)
      throw error(
        response.status === 429 ? 429 : 502,
        `DeepSeek 服务请求失败（${response.status}）`,
      );
    const content = (await response.json())?.choices?.[0]?.message?.content;
    if (!content) throw error(502, "DeepSeek 返回空结果");
    try {
      return JSON.parse(content);
    } catch {
      throw error(502, "DeepSeek 返回的不是有效 JSON");
    }
  } catch (e) {
    if (e.name === "AbortError")
      throw error(504, "DeepSeek 请求超时，请稍后重试");
    throw e;
  } finally {
    clearTimeout(timer);
    inFlight--;
  }
}
function consent(body) {
  if (body?.external_processing_consent !== true)
    throw error(400, "请先确认相关文本允许发送至 DeepSeek");
}
async function generateRule(userId, body) {
  consent(body);
  if (typeof body.intent !== "string" || !body.intent.trim())
    throw error(400, "请填写希望检查什么");
  const ids = Array.isArray(body.document_ids) ? body.document_ids : [];
  if (ids.length < 1 || ids.length > 5)
    throw error(400, "请选择 1–5 份示例 PDF");
  const documents = [];
  for (const id of ids) {
    const d = await repository.findDocument(userId, id);
    if (!d) throw error(404, "示例资料不存在或无权访问");
    if (!d.annotations.length)
      throw error(400, `示例“${d.source_filename}”尚未完成标注`);
    documents.push(d);
  }
  const value = await modelJson(
    "你是论文规范规则辅助生成器。只返回 JSON 对象，不要虚构证据。规则应可供人工复核。",
    JSON.stringify({
      intent: body.intent.trim().slice(0, 3000),
      examples: documents.map((d) => ({
        filename: d.source_filename,
        annotations: d.annotations,
      })),
    }),
  );
  return validateModelRule(value);
}
async function testRule(userId, body) {
  consent(body);
  const input = validateRuleInput({
    ...body,
    status: body.status || "enabled",
  });
  const ids = Array.isArray(body.document_ids) ? body.document_ids : [];
  if (!ids.length) throw error(400, "请选择已标注的示例 PDF");
  const docs = [];
  for (const id of ids) {
    const d = await repository.findDocument(userId, id);
    if (!d) throw error(404, "示例资料不存在或无权访问");
    docs.push(d);
  }
  const value = await modelJson(
    '你是论文规则试跑器。基于给出的示例标注验证规则。只返回 JSON：{"rule_results":[{"rule_id":"trial","outcome":"pass|issue|not_applicable|undetermined","conclusion":"","suggestion":"","evidence":[{"page_number":1,"text_excerpt":"","bounding_rect":null}]}]}。不得把未知内容判断为通过。',
    JSON.stringify({
      rule: input.definition,
      examples: docs.map((d) => ({
        filename: d.source_filename,
        annotations: d.annotations,
      })),
    }),
  );
  return { rule_results: validateModelResult(value) };
}
async function runReport(userId, buffer, sourceFilename, body) {
  consent(body);
  validatePdf(buffer);
  const ids = Array.isArray(body.rule_ids) ? body.rule_ids : [];
  if (!ids.length || ids.length > MAX_RULES_PER_RUN)
    throw error(400, `请选择 1–${MAX_RULES_PER_RUN} 条个人规则`);
  const rules = [];
  for (const id of ids) {
    const r = await repository.findRule(userId, id);
    if (!r) throw error(404, "规则不存在或无权访问");
    if (r.status !== "enabled") throw error(400, `规则“${r.name}”当前已停用`);
    rules.push(r);
  }
  const text = await extractText(buffer);
  const value = await modelJson(
    '你是论文规则检测辅助工具。只依据待检文本与规则判断，返回 JSON：{"rule_results":[{"rule_id":"","outcome":"pass|issue|not_applicable|undetermined","conclusion":"","suggestion":"","evidence":[{"page_number":1,"text_excerpt":"","bounding_rect":null}]}]}。每条 evidence 必须来自提供文本，无法定位时用 page_number 1 且明确说明。结果需人工复核。',
    JSON.stringify({
      rules: rules.map((r) => ({
        id: r.id,
        name: r.name,
        definition: r.definition,
      })),
      document_text: text,
    }),
  );
  const results = validateModelResult(value);
  const result = {
    disclaimer: "本报告为基于所选文本片段的辅助判断，必须由人工复核。",
    rule_results: results,
    summary: {
      rule_count: rules.length,
      issue_count: results.filter((x) => x.outcome === "issue").length,
      pass_count: results.filter((x) => x.outcome === "pass").length,
      undetermined_count: results.filter((x) => x.outcome === "undetermined")
        .length,
    },
  };
  return repository.createReport(
    userId,
    sourceFilename,
    buffer,
    rules.map((r) => ({
      rule_id: r.id,
      name: r.name,
      version: r.version,
      definition: r.definition,
    })),
    result,
  );
}
module.exports = {
  MAX_PDF_BYTES,
  validatePdf,
  validateAnnotations,
  validateRuleInput,
  generateRule,
  testRule,
  runReport,
  extractText,
};
