const {
  createCorpusSample,
  deleteCorpusSample,
  listCorpusSamples,
} = require('./duplicationCorpusRepository');

const MAX_CORPUS_SAMPLE_BYTES = 50 * 1024 * 1024;
const ALLOWED_CORPUS_FILE_EXTENSIONS = ['.txt', '.md', '.pdf'];

function serviceError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function requireSchoolAdmin(user, action = '管理') {
  if (!user) {
    throw serviceError(401, '请先登录');
  }
  if (user.role !== 'SCHOOL_ADMIN') {
    throw serviceError(403, `仅学校管理人员可${action}本地比对样本库`);
  }
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function validateYear(value) {
  const year = typeof value === 'number' ? value : Number(value);
  const currentYear = new Date().getFullYear();
  if (!Number.isInteger(year) || year < 1800 || year > currentYear + 1) {
    throw serviceError(400, '年份必须是合理的数字年份');
  }
  return year;
}

function getFileExtension(fileName) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

function validateSourceMetadata(sourceType, sourceFilename) {
  if (!['paste', 'file'].includes(sourceType)) {
    throw serviceError(400, '来源类型必须是 paste 或 file');
  }

  if (sourceType === 'file') {
    const fileName = normalizeText(sourceFilename);
    if (!fileName || !ALLOWED_CORPUS_FILE_EXTENSIONS.includes(getFileExtension(fileName))) {
      throw serviceError(400, '仅支持 .txt、.md 或 .pdf 文件样本');
    }
    return fileName;
  }

  return null;
}

function validateCreatePayload(payload = {}) {
  const title = normalizeText(payload.title);
  const subject = normalizeText(payload.subject);
  const content = normalizeText(payload.content);

  if (!title) {
    throw serviceError(400, '标题不能为空');
  }
  if (!subject) {
    throw serviceError(400, '学科不能为空');
  }
  if (!content) {
    throw serviceError(400, '样本文本不能为空');
  }
  if (Buffer.byteLength(content, 'utf8') > MAX_CORPUS_SAMPLE_BYTES) {
    throw serviceError(413, '样本文本不能超过 50 MB');
  }

  const year = validateYear(payload.year);
  const sourceType = payload.source_type;
  const sourceFilename = validateSourceMetadata(sourceType, payload.source_filename);

  return {
    title,
    subject,
    year,
    content,
    source_type: sourceType,
    source_filename: sourceFilename,
  };
}

async function listDuplicationCorpusSamples(user) {
  requireSchoolAdmin(user);
  return listCorpusSamples();
}

async function createDuplicationCorpusSample(user, payload) {
  requireSchoolAdmin(user, '新增');
  const sample = validateCreatePayload(payload);
  return createCorpusSample({
    ...sample,
    created_by: user.id,
  });
}

async function deleteDuplicationCorpusSample(user, sampleId) {
  requireSchoolAdmin(user, '删除');
  const normalizedSampleId = normalizeText(sampleId);
  if (!normalizedSampleId) {
    throw serviceError(400, '样本 ID 不能为空');
  }

  const deleted = await deleteCorpusSample(normalizedSampleId);
  if (!deleted) {
    throw serviceError(404, '样本不存在');
  }
}

module.exports = {
  ALLOWED_CORPUS_FILE_EXTENSIONS,
  MAX_CORPUS_SAMPLE_BYTES,
  createDuplicationCorpusSample,
  deleteCorpusSample,
  deleteDuplicationCorpusSample,
  listDuplicationCorpusSamples,
  createCorpusSample,
};
