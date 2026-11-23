CREATE TABLE IF NOT EXISTS paper_lint_credit_accounts (
  user_id TEXT PRIMARY KEY REFERENCES auth_users(id) ON DELETE CASCADE,
  granted_nano INTEGER NOT NULL DEFAULT 100000000000 CHECK(granted_nano >= 0),
  spent_nano INTEGER NOT NULL DEFAULT 0 CHECK(spent_nano >= 0),
  reserved_nano INTEGER NOT NULL DEFAULT 0 CHECK(reserved_nano >= 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK(spent_nano + reserved_nano <= granted_nano)
);
CREATE TRIGGER IF NOT EXISTS paper_lint_credit_initial_grant
AFTER INSERT ON auth_users BEGIN
  INSERT OR IGNORE INTO paper_lint_credit_accounts(user_id) VALUES (NEW.id);
END;
INSERT OR IGNORE INTO paper_lint_credit_accounts(user_id) SELECT id FROM auth_users;
CREATE TABLE IF NOT EXISTS paper_lint_credit_operations (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES paper_lint_jobs(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  job_attempt INTEGER NOT NULL,
  owner_pid INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('active','closing','closed')),
  created_at TEXT NOT NULL,
  finished_at TEXT,
  UNIQUE(job_id,job_attempt)
);
CREATE TABLE IF NOT EXISTS paper_lint_credit_calls (
  id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL REFERENCES paper_lint_credit_operations(id) ON DELETE CASCADE,
  rule_id TEXT NOT NULL,model TEXT NOT NULL,rate_version TEXT NOT NULL,rates_json TEXT NOT NULL,
  input_bound INTEGER NOT NULL,output_bound INTEGER NOT NULL,
  reserved_nano INTEGER NOT NULL CHECK(reserved_nano >= 0),
  charged_nano INTEGER NOT NULL DEFAULT 0 CHECK(charged_nano >= 0),
  status TEXT NOT NULL CHECK(status IN ('reserved','settled','released','unknown','invalid_usage')),
  input_tokens INTEGER,cached_tokens INTEGER,output_tokens INTEGER,usage_json TEXT,failure_code TEXT,
  worker_pid INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credit_call_operation_status ON paper_lint_credit_calls(operation_id,status);
CREATE INDEX IF NOT EXISTS idx_credit_operation_user ON paper_lint_credit_operations(user_id,state);
