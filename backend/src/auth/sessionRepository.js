const { get, run } = require('../database');

async function findUserByUsername(username) {
  return get(
    `SELECT id, username, password_hash AS passwordHash, role, college_id AS collegeId,
            supervisor_id AS supervisorId, scope
       FROM auth_users
      WHERE username = ?`,
    [username],
  );
}

async function findUserById(userId) {
  return get(
    `SELECT id, username, role, college_id AS collegeId, supervisor_id AS supervisorId, scope
       FROM auth_users
      WHERE id = ?`,
    [userId],
  );
}

async function createSession(sessionId, userId, expiresAt) {
  await run(
    `INSERT INTO auth_sessions (id, user_id, expires_at)
     VALUES (?, ?, ?)`,
    [sessionId, userId, expiresAt],
  );
}

async function findSession(sessionId) {
  return get(
    `SELECT sessions.id, sessions.expires_at AS expiresAt, users.id AS userId,
            users.username, users.role, users.college_id AS collegeId,
            users.supervisor_id AS supervisorId, users.scope
       FROM auth_sessions sessions
       JOIN auth_users users ON users.id = sessions.user_id
      WHERE sessions.id = ?`,
    [sessionId],
  );
}

async function deleteSession(sessionId) {
  await run('DELETE FROM auth_sessions WHERE id = ?', [sessionId]);
}

module.exports = {
  findUserByUsername,
  findUserById,
  createSession,
  findSession,
  deleteSession,
};
