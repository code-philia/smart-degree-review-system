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
      `CREATE TABLE IF NOT EXISTS demo_seed_metadata (
        demo_key TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        seeded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS normative_rule_drafts (
        id TEXT PRIMARY KEY,
        import_batch_id TEXT NOT NULL,
        scope_level TEXT NOT NULL CHECK (scope_level IN ('school', 'college')),
        college_id TEXT,
        rule_id TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        message TEXT NOT NULL,
        params_json TEXT NOT NULL,
        updated_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (scope_level, college_id, rule_id)
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS normative_detection_tasks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed')),
        source_type TEXT NOT NULL CHECK (source_type IN ('paste', 'file')),
        source_filename TEXT,
        original_text TEXT NOT NULL,
        rule_snapshot_json TEXT NOT NULL,
        issues_json TEXT NOT NULL,
        severity_counts_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS paper_lint_reports (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        source_filename TEXT NOT NULL,
        source_pdf_path TEXT NOT NULL,
        selected_rule_ids_json TEXT NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE INDEX IF NOT EXISTS idx_paper_lint_reports_user_created
       ON paper_lint_reports (user_id, created_at DESC);`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS duplication_corpus_samples (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        subject TEXT NOT NULL,
        year INTEGER NOT NULL,
        content TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK (source_type IN ('paste', 'file')),
        source_filename TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES auth_users(id) ON DELETE RESTRICT
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS duplication_detection_reports (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK (source_type IN ('paste', 'file')),
        source_filename TEXT,
        original_text TEXT NOT NULL,
        total_similarity_rate REAL NOT NULL,
        writing_risk_score REAL NOT NULL,
        sample_count INTEGER NOT NULL,
        report_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS whole_polish_results (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK (source_type IN ('paste', 'file')),
        source_filename TEXT,
        original_text TEXT NOT NULL,
        polished_text TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('basic', 'standard', 'enhanced')),
        changes_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS local_polish_results (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        original_text TEXT NOT NULL,
        polished_text TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('basic', 'standard', 'enhanced')),
        rule_version TEXT NOT NULL,
        changes_json TEXT NOT NULL,
        diff_segments_json TEXT NOT NULL,
        source_result_id TEXT,
        retry_of TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS innovation_assessment_snapshots (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        thesis_title TEXT NOT NULL,
        degree_type TEXT NOT NULL CHECK (degree_type IN ('doctoral', 'master')),
        primary_discipline TEXT NOT NULL,
        secondary_discipline TEXT NOT NULL,
        research_direction TEXT NOT NULL,
        input_snapshot_json TEXT NOT NULL,
        scoring_snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS ai_review_runs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        thesis_title TEXT NOT NULL,
        template_id TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK (source_type IN ('paste', 'file')),
        source_filename TEXT,
        original_text TEXT NOT NULL,
        section_snapshot_json TEXT NOT NULL,
        reference_count INTEGER NOT NULL,
        character_count INTEGER NOT NULL,
        normative_issues_json TEXT NOT NULL,
        score_items_json TEXT NOT NULL,
        total_score INTEGER NOT NULL,
        result_label TEXT NOT NULL,
        missing_sections_json TEXT NOT NULL,
        rubric_snapshot_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS report_submissions (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        supervisor_id TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK (source_type IN ('normative', 'duplication', 'innovation', 'ai_review')),
        report_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        FOREIGN KEY (supervisor_id) REFERENCES auth_users(id) ON DELETE RESTRICT
      );`,
    );

    await runStatement(
      database,
      `UPDATE report_submissions
          SET status = status
        WHERE status IN ('submitted_pending_review', 'review_completed_feedback', 'student_viewed_feedback');`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS supervisor_review_feedback (
        id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL UNIQUE,
        supervisor_id TEXT NOT NULL,
        annotations_json TEXT NOT NULL,
        overall_evaluation TEXT NOT NULL,
        improvement_suggestions TEXT,
        locked_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (submission_id) REFERENCES report_submissions(id) ON DELETE CASCADE,
        FOREIGN KEY (supervisor_id) REFERENCES auth_users(id) ON DELETE RESTRICT
      );`,
    );

    await runStatement(
      database,
      `CREATE TABLE IF NOT EXISTS in_app_todos (
        id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        assignee_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'done')),
        title TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (submission_id) REFERENCES report_submissions(id) ON DELETE CASCADE,
        FOREIGN KEY (assignee_id) REFERENCES auth_users(id) ON DELETE CASCADE,
        FOREIGN KEY (actor_id) REFERENCES auth_users(id) ON DELETE CASCADE
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
