const db = require('../database/db_runtime');

async function listSupervisorReviewTodos() {
  throw Object.assign(new Error('Supervisor review queue repository is not implemented yet'), { status: 501 });
}

async function countIncompleteSupervisorReviewTodos() {
  throw Object.assign(new Error('Supervisor review queue count repository is not implemented yet'), { status: 501 });
}

module.exports = {
  countIncompleteSupervisorReviewTodos,
  listSupervisorReviewTodos,
};
