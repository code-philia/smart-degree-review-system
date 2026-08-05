const ledgerRecordsRepository = require('./ledgerRecordsRepository');
const qualityDashboardRepository = require('./qualityDashboardRepository');
const { ALLOWED_LEDGER_RECORD_ROLES, buildLedgerAccessScope } = require('./ledgerRecordsService');

const ALLOWED_QUALITY_DASHBOARD_ROLES = ALLOWED_LEDGER_RECORD_ROLES;

function toQualityDashboardFilters(query = {}) {
  return ledgerRecordsRepository.normalizeLedgerFilters({
    student: query.student,
    detection_type: query.detection_type,
    from: query.from,
    to: query.to,
    latest_only: query.latest_only,
  });
}

async function getQualityDashboardForUser(user, query = {}) {
  const scope = buildLedgerAccessScope(user);
  return qualityDashboardRepository.summarizeQualityDashboard(scope, toQualityDashboardFilters(query));
}

module.exports = {
  ALLOWED_QUALITY_DASHBOARD_ROLES,
  getQualityDashboardForUser,
  toQualityDashboardFilters,
};
