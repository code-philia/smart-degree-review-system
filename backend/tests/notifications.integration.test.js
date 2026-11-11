import request from "supertest";
import { beforeAll, afterAll, expect, it } from "vitest";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const {
  createTestDatabaseHarness,
  run,
  get,
  all,
  closeDb,
  initializeDatabase,
} = require("../src/database");
const { createUserSession } = require("../src/auth/sessionService");
const app = require("../src/app");
let harness, cookie;
const stamp = "2099-01-01T00:00:00.000Z";
async function job(
  id,
  status,
  owner = "student01",
  cancelled = null,
  time = stamp,
) {
  await run(
    `INSERT INTO paper_lint_jobs(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,external_consent,status,attempts,created_at,updated_at,cancelled_at)
    VALUES (?,?,?,'/fixture.pdf','[]',0,?,1,?,?,?)`,
    [id, owner, `学位论文_${id}_完整文件名.pdf`, status, time, time, cancelled],
  );
  if (status === "completed") {
    await run(
      `INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES (?,?,?,'/fixture.pdf','[]','{"unchanged":true}',?)`,
      [id, owner, `学位论文_${id}_完整文件名.pdf`, time],
    );
    await run("UPDATE paper_lint_jobs SET report_id=? WHERE id=?", [id, id]);
  }
}
async function mail(id, status) {
  await run(
    `INSERT INTO report_email_outbox(job_id,user_id,report_id,recipient,status,attempts,next_attempt_at,sent_at,created_at,updated_at)
    VALUES (?,'student01',?,'student@example.com',?,5,?,?,?,?)`,
    [id, id, status, stamp, status === "sent" ? stamp : null, stamp, stamp],
  );
}
const feed = () => request(app).get("/api/notifications").set("Cookie", cookie);
beforeAll(async () => {
  harness = createTestDatabaseHarness({
    label: "notification-center",
    seedDefault: true,
  });
  await harness.setup();
  const session = await createUserSession(
    await get("SELECT * FROM auth_users WHERE id='student01'"),
  );
  cookie = `arc_session=${session.sessionId}`;
  await job("ready", "completed");
  await mail("ready", "sent");
  await job("broken", "failed");
  await job("mail-broken", "completed");
  await mail("mail-broken", "failed");
  await job("retry", "completed");
  await mail("retry", "pending");
  await job("cancelled", "failed", "student01", stamp);
  await job("other", "completed", "supervisor01");
  await job("old", "completed", "student01", null, "2000-01-01T00:00:00.000Z");
});
afterAll(async () => {
  await harness?.cleanup();
});
it("requires authentication and exposes all four event types only for the owner", async () => {
  await request(app).get("/api/notifications").expect(401);
  const { body } = await feed().expect(200);
  expect(body.items.map((x) => x.kind)).toEqual(
    expect.arrayContaining([
      "report_ready",
      "mail_sent",
      "detection_failed",
      "mail_failed",
    ]),
  );
  expect(body.items).toHaveLength(6);
  expect(body.unreadCount).toBe(6);
  expect(
    body.items.every(
      (x) =>
        x.filename.startsWith("学位论文_") &&
        !x.id.includes("other") &&
        !x.id.includes("old") &&
        !x.id.includes("cancelled"),
    ),
  ).toBe(true);
  expect(body.items.find((x) => x.id === "report_ready:ready")).toMatchObject({
    filename: "学位论文_ready_完整文件名.pdf",
    href: "/reports/pdf/ready",
    read: false,
  });
  expect(body.items.find((x) => x.id === "detection_failed:broken").href).toBe(
    "/paper-upload",
  );
  expect(JSON.stringify(body)).not.toMatch(
    /fixture\.pdf|password_hash|error_message/,
  );
});
it("persists per-item reads and rejects cross-owner or invented ids atomically", async () => {
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .send({ ids: ["report_ready:ready", "report_ready:other"] })
    .expect(404);
  expect((await feed()).body.unreadCount).toBe(6);
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .send({ ids: ["report_ready:ready"] })
    .expect(200);
  expect(
    (await feed()).body.items.find((x) => x.id === "report_ready:ready").read,
  ).toBe(true);
  expect((await feed()).body.unreadCount).toBe(5);
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .send({ ids: ["report_ready:ready"] })
    .expect(200);
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .send({ ids: [] })
    .expect(400);
});
it("does not widen notification ownership for administrators or accept oversized acknowledgements", async () => {
  const admin = await createUserSession(
    await get("SELECT * FROM auth_users WHERE id='school_admin01'"),
  );
  const ownCookie = `arc_session=${admin.sessionId}`;
  const response = await request(app)
    .get("/api/notifications")
    .set("Cookie", ownCookie)
    .expect(200);
  expect(response.headers["cache-control"]).toBe("no-store");
  expect(response.body).toEqual({ items: [], unreadCount: 0, total: 0 });
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", ownCookie)
    .send({ ids: ["report_ready:ready"] })
    .expect(404);
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .send({ ids: Array(51).fill("report_ready:ready") })
    .expect(400);
  await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .send({ ids: ["report_ready:../../secret"] })
    .expect(400);
});
it("returns safe JSON for malformed request bodies without disclosing server paths", async () => {
  const response = await request(app)
    .post("/api/notifications/read")
    .set("Cookie", cookie)
    .set("Content-Type", "application/json")
    .send("{")
    .expect(400);
  expect(response.type).toBe("application/json");
  expect(response.body.message).toBe("Invalid notification request");
  expect(response.text).not.toMatch(/node_modules|SyntaxError|\/data\//);
});
it("marks current notices read but leaves later arrivals unread and limits the feed", async () => {
  await request(app)
    .post("/api/notifications/read-all")
    .set("Cookie", cookie)
    .send({})
    .expect(200);
  expect((await feed()).body.unreadCount).toBe(0);
  await job("later", "completed");
  const { body } = await request(app)
    .get("/api/notifications?limit=2")
    .set("Cookie", cookie)
    .expect(200);
  expect(body.items).toHaveLength(2);
  expect(body.total).toBe(7);
  expect(body.unreadCount).toBe(1);
});
it("keeps activation time and read receipts after reopening the database, and never changes results", async () => {
  const before = await get(
    "SELECT starts_at FROM app_notification_config WHERE id=1",
  );
  await closeDb();
  await initializeDatabase();
  expect(
    await get("SELECT starts_at FROM app_notification_config WHERE id=1"),
  ).toEqual(before);
  expect(
    (await feed()).body.items.find((x) => x.id === "report_ready:ready").read,
  ).toBe(true);
  expect(
    await get("SELECT result_json FROM paper_lint_reports WHERE id='ready'"),
  ).toEqual({ result_json: '{"unchanged":true}' });
  expect(
    await get(
      "SELECT status,attempts FROM report_email_outbox WHERE job_id='ready'",
    ),
  ).toEqual({ status: "sent", attempts: 5 });
  await run("DELETE FROM paper_lint_reports WHERE id='ready'");
  expect((await feed()).body.items.some((x) => x.id.endsWith(":ready"))).toBe(
    false,
  );
});
