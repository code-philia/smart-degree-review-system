const fs = require('fs/promises');
const path = require('path');
const { execFile } = require('child_process');
const { promisify } = require('util');
const { appendEvidence } = require('./legacyRepairAdapter');
const { buildArchiveRepairRequest, getArchiveFinding } = require('./repairSuggestionService');

const execFileAsync = promisify(execFile);
const SCRIPT = path.resolve(__dirname, '../../scripts/repair_pdf_evidence.py');
const DEFAULT_ARCHIVE_ROOT = '/opt/sjtu-archive-479';

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

async function resolveArchivePdfPath(relativePath, archiveRoot = process.env.ARCHIVE_SCAN_ROOT || DEFAULT_ARCHIVE_ROOT) {
  const root = await fs.realpath(archiveRoot);
  const candidate = await fs.realpath(path.resolve(root, relativePath));
  if (!candidate.startsWith(root + path.sep) || !candidate.toLowerCase().endsWith('.pdf')) {
    throw problem(404, '归档论文不存在');
  }
  const stat = await fs.stat(candidate);
  if (!stat.isFile()) throw problem(404, '归档论文不存在');
  return candidate;
}

async function extractPdfContext(pdfPath, location) {
  const page = Number(location?.page_number || location?.bounding_rect?.page_number);
  if (!Number.isSafeInteger(page) || page < 1) throw problem(422, '告警缺少有效 PDF 页码');
  const box = location?.bounding_rect || {};
  const python = process.env.REPAIR_EVIDENCE_PYTHON || process.env.SIX_RULE_PYTHON ||
    process.env.FIVE_RULE_PYTHON || process.env.REVIEW_PILOT_PYTHON || 'python3';
  let stdout;
  try {
    ({ stdout } = await execFileAsync(python, [SCRIPT, '--pdf', pdfPath, '--page', String(page),
      ...(['x1', 'y1', 'x2', 'y2'].every((key) => Number.isFinite(box[key]))
        ? ['--x1', String(box.x1), '--y1', String(box.y1), '--x2', String(box.x2), '--y2', String(box.y2)]
        : [])], {
      timeout: 30000, maxBuffer: 1024 * 1024, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    }));
  } catch (error) {
    const unavailable = error.code === 'ENOENT' || /No module named ['"]?pymupdf/.test(error.stderr || '');
    throw problem(unavailable ? 503 : 502, unavailable
      ? 'PDF 上下文提取器不可用：请配置 REPAIR_EVIDENCE_PYTHON 并安装 PyMuPDF'
      : 'PDF 上下文提取失败，请检查 PDF 或服务器日志');
  }
  try {
    const output = JSON.parse(stdout);
    if (!output || typeof output.text !== 'string') throw new Error('invalid output');
    return output;
  } catch {
    throw problem(502, 'PDF 上下文提取器返回了无法解析的结果');
  }
}

async function buildArchiveRepairRequestWithPdfContext({ jobId, documentId, ruleId, findingId }) {
  const request = await buildArchiveRepairRequest({ jobId, documentId, ruleId, findingId });
  const { document, finding } = await getArchiveFinding(jobId, documentId, ruleId, findingId);
  const pdfPath = await resolveArchivePdfPath(document.relative_path);
  const extracted = await extractPdfContext(pdfPath, finding.location);
  if (!extracted.text.trim()) throw problem(422, 'PDF 目标位置未提取到可用文本上下文');
  return appendEvidence(request, {
    evidence_id: `pdf-context-${request.evidence.length + 1}`,
    source_kind: 'pdf_text',
    text: extracted.text,
    page_number: extracted.page_number,
    location: finding.location,
    source_ref: `legacy_archive:pdf_context:${document.relative_path}#page=${extracted.page_number}`,
  });
}

module.exports = {
  buildArchiveRepairRequestWithPdfContext,
  extractPdfContext,
  resolveArchivePdfPath,
};
