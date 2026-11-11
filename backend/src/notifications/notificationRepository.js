const { all, withTransaction } = require("../database");

// Read existing states without changing detection results or mail delivery.
// One persisted activation time prevents a first-release historical backlog.
const EVENTS = `WITH owned_jobs AS (
  SELECT * FROM paper_lint_jobs WHERE user_id = ?
), events AS (
  SELECT 'report_ready:' || j.id AS id, 'report_ready' AS kind,
    j.source_filename AS filename, r.id AS report_id, r.created_at AS created_at, NULL AS recipient
  FROM owned_jobs j JOIN paper_lint_reports r ON r.id=j.report_id AND r.user_id=j.user_id
  WHERE j.status='completed' AND julianday(r.created_at) >= (SELECT julianday(starts_at) FROM app_notification_config WHERE id=1)
  UNION ALL
  SELECT 'detection_failed:' || j.id, 'detection_failed', j.source_filename, NULL, j.updated_at, NULL
  FROM owned_jobs j WHERE j.status='failed' AND j.cancelled_at IS NULL
    AND julianday(j.updated_at) >= (SELECT julianday(starts_at) FROM app_notification_config WHERE id=1)
  UNION ALL
  SELECT CASE o.status WHEN 'sent' THEN 'mail_sent:' ELSE 'mail_failed:' END || j.id,
    CASE o.status WHEN 'sent' THEN 'mail_sent' ELSE 'mail_failed' END,
    j.source_filename, r.id, CASE o.status WHEN 'sent' THEN o.sent_at ELSE o.updated_at END, o.recipient
  FROM owned_jobs j JOIN report_email_outbox o ON o.job_id=j.id AND o.user_id=j.user_id
    JOIN paper_lint_reports r ON r.id=o.report_id AND r.user_id=j.user_id
  WHERE o.status IN ('sent','failed')
    AND julianday(CASE o.status WHEN 'sent' THEN o.sent_at ELSE o.updated_at END)
      >= (SELECT julianday(starts_at) FROM app_notification_config WHERE id=1)
)`;

async function listNotifications(userId, limit = 25) {
  const rows = await all(
    `${EVENTS}
    SELECT e.*, n.read_at, COUNT(*) OVER () AS total,
      SUM(CASE WHEN n.notification_id IS NULL THEN 1 ELSE 0 END) OVER () AS unread_count
    FROM events e LEFT JOIN user_notification_reads n ON n.notification_id=e.id AND n.user_id=?
    ORDER BY julianday(e.created_at) DESC, e.id ASC LIMIT ?`,
    [userId, userId, limit],
  );
  return {
    items: rows.map((row) => ({
      id: row.id,
      kind: row.kind,
      filename: row.filename,
      createdAt: row.created_at,
      recipient: row.recipient,
      read: !!row.read_at,
      href: row.report_id
        ? `/reports/pdf/${encodeURIComponent(row.report_id)}`
        : "/paper-upload",
    })),
    unreadCount: Number(rows[0]?.unread_count || 0),
    total: Number(rows[0]?.total || 0),
  };
}

async function markNotificationsRead(userId, ids = null) {
  return withTransaction(async (tx) => {
    const selection = ids
      ? ` WHERE id IN (${ids.map(() => "?").join(",")})`
      : "";
    const rows = await tx.all(`${EVENTS} SELECT id FROM events${selection}`, [
      userId,
      ...(ids || []),
    ]);
    if (ids && rows.length !== new Set(ids).size) return false;
    const readAt = new Date().toISOString();
    for (const { id } of rows) {
      await tx.run(
        "INSERT OR IGNORE INTO user_notification_reads(user_id,notification_id,read_at) VALUES (?,?,?)",
        [userId, id, readAt],
      );
    }
    return true;
  });
}

module.exports = { listNotifications, markNotificationsRead };
