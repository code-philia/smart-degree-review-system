const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const DEFAULT_DB_FILENAME = 'database.db';

let db = null;
let initPromise = null;
let currentDbPath = resolveDbPath(
  process.env.ARC_DB_FILE || process.env.DATABASE_FILE || DEFAULT_DB_FILENAME,
);

function resolveDbPath(inputPath = DEFAULT_DB_FILENAME) {
  const candidate = String(inputPath || DEFAULT_DB_FILENAME).trim() || DEFAULT_DB_FILENAME;
  return path.resolve(process.cwd(), candidate);
}

function ensureDbDirectory(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function getDbPath() {
  return currentDbPath;
}

async function setDbPath(nextPath) {
  const resolvedPath = resolveDbPath(nextPath);
  if (resolvedPath === currentDbPath) {
    return currentDbPath;
  }

  await closeDb();
  currentDbPath = resolvedPath;
  return currentDbPath;
}

function getDb() {
  if (!db) {
    ensureDbDirectory(currentDbPath);
    db = new sqlite3.Database(currentDbPath);
  }
  return db;
}

function runStatement(database, sql) {
  return new Promise((resolve, reject) => {
    database.run(sql, (err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

async function initializeDatabase(options = {}) {
  if (options.dbPath) {
    await setDbPath(options.dbPath);
  }
  if (options.reset) {
    await resetDatabaseFile();
  }
  if (initPromise) {
    return initPromise;
  }

  const database = getDb();
  initPromise = (async () => {
    await runStatement(database, 'PRAGMA foreign_keys = ON;');

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS auth_users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN')),
        college_id TEXT,
        supervisor_id TEXT,
        scope TEXT NOT NULL CHECK (scope IN ('COLLEGE', 'SCHOOL')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS auth_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS normative_rule_overrides (
        id TEXT PRIMARY KEY,
        scope_level TEXT NOT NULL CHECK (scope_level IN ('school', 'college')),
        college_id TEXT,
        rule_id TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        match_params_json TEXT NOT NULL,
        prompt TEXT NOT NULL,
        updated_by TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (scope_level, college_id, rule_id)
      );`,
    );

    return database;

    /**
     * Guide model instructions:
     * 1. Use CREATE TABLE IF NOT EXISTS to create new tables.
     * 2. When adding fields, use ALTER TABLE ... ADD COLUMN ... and guard it with existence checks or tolerant error handling.
     * 3. Keep schema evolution idempotent and centralized in this file.
     * 4. Reuse `db_runtime.js` for CRUD helpers and `test_harness.js` for test DB lifecycle instead of re-implementing one-off connection logic elsewhere.
     */
  })();

  try {
    await initPromise;
  } catch (error) {
    initPromise = null;
    throw error;
  }

  return database;
}

function closeDb() {
  if (!db) {
    initPromise = null;
    return Promise.resolve();
  }

  const currentDb = db;
  db = null;
  initPromise = null;
  return new Promise((resolve, reject) => {
    currentDb.close((err) => {
      if (err) {
        reject(err);
        return;
      }
      resolve();
    });
  });
}

async function removeDatabaseFile(targetPath = currentDbPath) {
  const resolvedPath = resolveDbPath(targetPath);
  if (resolvedPath === currentDbPath) {
    await closeDb();
  }
  if (fs.existsSync(resolvedPath)) {
    fs.rmSync(resolvedPath, { force: true });
  }
}

async function resetDatabaseFile(targetPath = currentDbPath) {
  await removeDatabaseFile(targetPath);
}

module.exports = {
  DEFAULT_DB_FILENAME,
  resolveDbPath,
  getDbPath,
  setDbPath,
  getDb,
  initializeDatabase,
  closeDb,
  removeDatabaseFile,
  resetDatabaseFile,
};
