function createQualityDashboardRepositoryError(message) {
  const error = new Error(message);
  error.code = 'QUALITY_DASHBOARD_REPOSITORY_NOT_IMPLEMENTED';
  return error;
}

async function summarizeQualityDashboard(scope, filters = {}) {
  throw createQualityDashboardRepositoryError(
    '群体质量仪表盘仓储尚未实现：需按权限范围、时间、学生和类型聚合规范分、原创参考分、创新参考分和评阅基础分',
  );
}

module.exports = {
  summarizeQualityDashboard,
};
