const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const {
  ALLOWED_LEDGER_RECORD_ROLES,
  exportLedgerRecordsCsvForUser,
  getLedgerRecordForUser,
  listLedgerRecordsForUser,
} = require('./ledgerRecordsService');

const router = express.Router();

function sendLedgerRecordsError(error, res, next) {
  if (error?.status) {
    res.status(error.status).json({ code: error.status, message: error.message });
    return;
  }
  if (error?.code === 'LEDGER_RECORDS_REPOSITORY_NOT_IMPLEMENTED') {
    res.status(501).json({ code: 501, message: error.message });
    return;
  }
  next(error);
}

router.get('/', requireAuth({ allowedRoles: ALLOWED_LEDGER_RECORD_ROLES }), async (req, res, next) => {
  try {
    const records = await listLedgerRecordsForUser(req.user, req.query || {});
    res.json({ records });
  } catch (error) {
    sendLedgerRecordsError(error, res, next);
  }
});

router.get('/export.csv', requireAuth({ allowedRoles: ALLOWED_LEDGER_RECORD_ROLES }), async (req, res, next) => {
  try {
    const csv = await exportLedgerRecordsCsvForUser(req.user, req.query || {});
    res
      .type('text/csv; charset=utf-8')
      .attachment('ledger-records.csv')
      .send(`\uFEFF${csv}`);
  } catch (error) {
    sendLedgerRecordsError(error, res, next);
  }
});

router.get('/:recordId', requireAuth({ allowedRoles: ALLOWED_LEDGER_RECORD_ROLES }), async (req, res, next) => {
  try {
    const record = await getLedgerRecordForUser(req.user, req.params.recordId);
    res.json(record);
  } catch (error) {
    sendLedgerRecordsError(error, res, next);
  }
});

module.exports = router;
