const reportSupervisorQueueRepository = require('./reportSupervisorQueueRepository');

const ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES = ['SUPERVISOR'];
const REPORT_SUPERVISOR_QUEUE_STATUSES = ['pending', 'done'];

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getCurrentUserId(user) {
  return user?.username || user?.id || null;
}

function ensureSupervisorQueueActor(user) {
  const supervisorId = getCurrentUserId(user);
  if (!supervisorId) {
    throw createHttpError(401, '请先登录后查看待批阅任务');
  }
  if (!ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES.includes(user.role)) {
    throw createHttpError(403, '仅导师可查看本人待批阅任务');
  }
  return { supervisorId };
}

function normalizeSupervisorQueueFilters(query = {}) {
  const filters = {
    student_id: typeof query.student_id === 'string' ? query.student_id.trim() : '',
    source_type: typeof query.source_type === 'string' ? query.source_type.trim() : '',
    status: typeof query.status === 'string' ? query.status.trim() : '',
  };

  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
}

async function listSupervisorReviewQueue(user, query = {}) {
  const { supervisorId } = ensureSupervisorQueueActor(user);
  return reportSupervisorQueueRepository.listSupervisorReviewTodos({
    supervisorId,
    filters: normalizeSupervisorQueueFilters(query),
  });
}

async function getSupervisorReviewQueueBadge(user) {
  const { supervisorId } = ensureSupervisorQueueActor(user);
  return reportSupervisorQueueRepository.countIncompleteSupervisorReviewTodos({ supervisorId });
}

module.exports = {
  ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES,
  REPORT_SUPERVISOR_QUEUE_STATUSES,
  ensureSupervisorQueueActor,
  getSupervisorReviewQueueBadge,
  listSupervisorReviewQueue,
  normalizeSupervisorQueueFilters,
};
