const express = require("express");
const { requireAuth } = require("../auth/authMiddleware");
const {
  listNotifications,
  markNotificationsRead,
} = require("./notificationRepository");
const router = express.Router();
router.use(requireAuth(), express.json({ limit: "8kb" }));
router.use((req, res, next) => {
  res.setHeader("Cache-Control", "no-store");
  next();
});

router.get("/", async (req, res, next) => {
  try {
    const raw = Number(req.query.limit || 25);
    const limit = Number.isInteger(raw) ? Math.max(1, Math.min(raw, 50)) : 25;
    res.json(await listNotifications(req.user.id, limit));
  } catch (error) {
    next(error);
  }
});
router.post("/read", async (req, res, next) => {
  const ids = req.body?.ids;
  if (
    !Array.isArray(ids) ||
    !ids.length ||
    ids.length > 50 ||
    ids.some(
      (id) =>
        typeof id !== "string" ||
        !/^(report_ready|mail_sent|mail_failed|detection_failed):[A-Za-z0-9_-]{1,100}$/.test(
          id,
        ),
    )
  ) {
    return res.status(400).json({ message: "Invalid notification ids" });
  }
  try {
    if (!(await markNotificationsRead(req.user.id, [...new Set(ids)])))
      return res.status(404).json({ message: "Notification not found" });
    res.json({ ok: true });
  } catch (error) {
    next(error);
  }
});
router.post("/read-all", async (req, res, next) => {
  try {
    await markNotificationsRead(req.user.id);
    res.json({ ok: true });
  } catch (error) {
    next(error);
  }
});
// Keep errors JSON-only here, including in a development preview.
router.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  if (error?.type === "entity.too.large")
    return res.status(413).json({ message: "Notification request too large" });
  if (error?.type === "entity.parse.failed")
    return res.status(400).json({ message: "Invalid notification request" });
  console.error("Notification API failed", error?.code || "unexpected_error");
  return res
    .status(500)
    .json({ message: "Notifications are temporarily unavailable" });
});
module.exports = router;
