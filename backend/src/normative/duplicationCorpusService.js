const {
  createCorpusSample,
  deleteCorpusSample,
  listCorpusSamples,
} = require('./duplicationCorpusRepository');

const MAX_CORPUS_SAMPLE_BYTES = 5 * 1024 * 1024;
const ALLOWED_CORPUS_FILE_EXTENSIONS = ['.txt', '.md'];

function notImplemented() {
  const error = new Error('本地比对样本库服务尚未实现');
  error.code = 'DUPLICATION_CORPUS_SERVICE_NOT_IMPLEMENTED';
  error.status = 501;
  return error;
}

async function listDuplicationCorpusSamples(user) {
  if (!user) {
    const error = new Error('请先登录');
    error.status = 401;
    throw error;
  }
  if (user.role !== 'SCHOOL_ADMIN') {
    const error = new Error('仅学校管理人员可管理本地比对样本库');
    error.status = 403;
    throw error;
  }
  return listCorpusSamples();
}

async function createDuplicationCorpusSample(user, payload) {
  void payload;
  if (!user) {
    const error = new Error('请先登录');
    error.status = 401;
    throw error;
  }
  if (user.role !== 'SCHOOL_ADMIN') {
    const error = new Error('仅学校管理人员可新增本地比对样本');
    error.status = 403;
    throw error;
  }
  throw notImplemented();
}

async function deleteDuplicationCorpusSample(user, sampleId) {
  void sampleId;
  if (!user) {
    const error = new Error('请先登录');
    error.status = 401;
    throw error;
  }
  if (user.role !== 'SCHOOL_ADMIN') {
    const error = new Error('仅学校管理人员可删除本地比对样本');
    error.status = 403;
    throw error;
  }
  throw notImplemented();
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
