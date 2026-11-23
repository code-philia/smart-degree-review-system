const { withTransaction } = require('../database');

const FEEDBACK_ANNOUNCEMENT_ID = 'feedback-2026-11-24';

async function claimFeedbackAnnouncement(userId, requestId) {
  return withTransaction(async ({ get, run }) => {
    await run(`INSERT INTO user_announcement_receipts (user_id, announcement_id, request_id)
    VALUES (?, ?, ?) ON CONFLICT (user_id, announcement_id) DO NOTHING`,
  [userId, FEEDBACK_ANNOUNCEMENT_ID, requestId]);
  const receipt = await get(`SELECT request_id FROM user_announcement_receipts
    WHERE user_id = ? AND announcement_id = ?`, [userId, FEEDBACK_ANNOUNCEMENT_ID]);
    return { announcement_id: FEEDBACK_ANNOUNCEMENT_ID, show: receipt?.request_id === requestId };
  });
}

module.exports = { claimFeedbackAnnouncement };
