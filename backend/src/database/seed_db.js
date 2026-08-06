const bcrypt = require('bcrypt');
const { closeDb } = require('./init_db');
const { withTransaction } = require('./db_runtime');

async function seedDatabase() {
  return withTransaction(async ({ run, get, all, exec }) => {
    void get;
    void all;
    void exec;

    const passwordHash = await bcrypt.hash('ArcDemo123!', 10);
    const demoUsers = [
      ['student01', 'student01', passwordHash, 'STUDENT', 'college01', 'supervisor01', 'COLLEGE'],
      ['supervisor01', 'supervisor01', passwordHash, 'SUPERVISOR', 'college01', null, 'COLLEGE'],
      ['college_admin01', 'college_admin01', passwordHash, 'COLLEGE_ADMIN', 'college01', null, 'COLLEGE'],
      ['school_admin01', 'school_admin01', passwordHash, 'SCHOOL_ADMIN', null, null, 'SCHOOL'],
    ];

    for (const user of demoUsers) {
      await run(
        `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(username) DO NOTHING`,
        user,
      );
    }

    /**
     * Guide model instructions:
     * 1. Use INSERT OR IGNORE / INSERT OR REPLACE / UPSERT semantics so repeated seeding is safe.
     * 2. Seed parent tables before child tables and keep fixtures minimal.
     * 3. Reuse this entrypoint from tests and dev scripts instead of duplicating insert logic in many files.
     * 4. If a test needs DB state, create an isolated test DB with `createTestDatabaseHarness()` from `test_harness.js`,
     *    seed only the rows needed by that suite, then clean the test DB up in teardown.
     */
  });
}

if (require.main === module) {
  seedDatabase()
    .then(() => closeDb())
    .catch((error) => {
      console.error('Database seed failed:', error);
      process.exitCode = 1;
    });
}

module.exports = seedDatabase;
module.exports.seedDatabase = seedDatabase;
module.exports.seed = seedDatabase;
