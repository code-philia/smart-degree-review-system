const STUDENT_QUALITY_METRIC_KEYS = ['normative', 'originality', 'innovation', 'review_base'];

function createStudentQualityPortraitRepositoryError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

async function getStudentQualityPortrait(_scope, _studentId, _filters = {}) {
  throw createStudentQualityPortraitRepositoryError(
    'STUDENT_QUALITY_PORTRAIT_REPOSITORY_NOT_IMPLEMENTED',
    '单学生质量画像聚合仓储尚未实现',
  );
}

module.exports = {
  STUDENT_QUALITY_METRIC_KEYS,
  getStudentQualityPortrait,
};
