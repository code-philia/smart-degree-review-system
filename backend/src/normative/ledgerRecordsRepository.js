const { all, get } = require('../database');

function normalizeLedgerFilters(filters = {}) {
  return {
    student: typeof filters.student === 'string' ? filters.student.trim() : '',
    detection_type: typeof filters.detection_type === 'string' ? filters.detection_type.trim() : '',
    from: typeof filters.from === 'string' ? filters.from.trim() : '',
    to: typeof filters.to === 'string' ? filters.to.trim() : '',
    latest_only: filters.latest_only === true || filters.latest_only === 'true',
  };
}

async function listLedgerRecords(_scope, _filters = {}) {
  await all('SELECT 1 AS ledger_contract_probe;');
  const error = new Error('Ledger record repository is not implemented');
  error.code = 'LEDGER_RECORDS_REPOSITORY_NOT_IMPLEMENTED';
  throw error;
}

async function findLedgerRecordById(_scope, _recordId) {
  await get('SELECT 1 AS ledger_contract_probe;');
  const error = new Error('Ledger record repository is not implemented');
  error.code = 'LEDGER_RECORDS_REPOSITORY_NOT_IMPLEMENTED';
  throw error;
}

module.exports = {
  findLedgerRecordById,
  listLedgerRecords,
  normalizeLedgerFilters,
};
