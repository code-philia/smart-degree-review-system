import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { getDbPath, setDbPath, getDb, initializeDatabase, closeDb, get, run, all } = require('../src/database');

it('adds the name field to an existing database while preserving accounts, sessions and reports across restarts', async () => {
  const previous = getDbPath();
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'arc-name-migration-'));
  try {
    await setDbPath(path.join(directory, 'existing.sqlite'));
    await new Promise((resolve, reject) => getDb().exec(`
      CREATE TABLE auth_users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, role TEXT NOT NULL, college_id TEXT,
        supervisor_id TEXT, scope TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
      INSERT INTO auth_users (id,username,password_hash,role,scope)
        VALUES ('existing-person','existing-account','existing-hash','SUPERVISOR','COLLEGE');
      CREATE TABLE auth_sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
      INSERT INTO auth_sessions (id,user_id,expires_at) VALUES ('existing-session','existing-person','2099-01-01');
      CREATE TABLE paper_lint_reports (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
        source_filename TEXT NOT NULL, source_pdf_path TEXT NOT NULL, selected_rule_ids_json TEXT NOT NULL,
        result_json TEXT NOT NULL, created_at TEXT NOT NULL);
      INSERT INTO paper_lint_reports VALUES ('existing-report','existing-person','existing.pdf','existing.pdf','[]','{}','2026-10-31');
    `, error => error ? reject(error) : resolve()));
    await initializeDatabase();
    expect((await all('PRAGMA table_info(auth_users)')).map(column => column.name)).toContain('display_name');
    await run("UPDATE auth_users SET display_name='张三' WHERE id='existing-person'");
    await closeDb();
    await initializeDatabase();
    expect(await get("SELECT username,password_hash,role,display_name FROM auth_users WHERE id='existing-person'"))
      .toEqual({ username: 'existing-account', password_hash: 'existing-hash', role: 'SUPERVISOR', display_name: '张三' });
    expect((await get("SELECT user_id FROM auth_sessions WHERE id='existing-session'")).user_id).toBe('existing-person');
    expect((await get("SELECT user_id FROM paper_lint_reports WHERE id='existing-report'")).user_id).toBe('existing-person');
  } finally {
    await closeDb();
    await setDbPath(previous);
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
