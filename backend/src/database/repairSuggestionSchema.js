const CREATE_TABLE = "CREATE TABLE IF NOT EXISTS repair_suggestions (\n      id TEXT PRIMARY KEY,\n      source_kind TEXT NOT NULL CHECK (source_kind IN ('legacy_archive', 'paper_ir')),\n      job_id TEXT NOT NULL,\n      document_id TEXT NOT NULL,\n      document_sha256 TEXT NOT NULL,\n      detector_version TEXT,\n      rule_id TEXT NOT NULL,\n      finding_id TEXT NOT NULL,\n      context_sha256 TEXT NOT NULL,\n      generation INTEGER NOT NULL DEFAULT 1,\n      status TEXT NOT NULL CHECK (status IN ('suggested', 'insufficient_context', 'evidence_conflict')),\n      provider TEXT NOT NULL,\n      model TEXT NOT NULL,\n      model_version TEXT NOT NULL,\n      prompt_version TEXT NOT NULL,\n      response_json TEXT NOT NULL,\n      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n      UNIQUE (job_id, document_id, rule_id, finding_id, context_sha256, model, model_version, prompt_version, generation)\n    );";
const COLUMNS = ['id','source_kind','job_id','document_id','document_sha256','detector_version','rule_id','finding_id','context_sha256','status','provider','model','model_version','prompt_version','response_json','created_at'];
const run = (db, sql) => new Promise((resolve, reject) => db.run(sql, error => error ? reject(error) : resolve()));
const all = (db, sql) => new Promise((resolve, reject) => db.all(sql, (error, rows) => error ? reject(error) : resolve(rows)));
async function ensureArchiveRepairSchema(database) {
  await run(database, CREATE_TABLE);
  const columns = await all(database, 'PRAGMA table_info(repair_suggestions)');
  if (!columns.some(column => column.name === 'generation')) {
    await run(database, 'BEGIN IMMEDIATE');
    try {
      await run(database, 'ALTER TABLE repair_suggestions RENAME TO repair_suggestions_before_versions');
      await run(database, CREATE_TABLE);
      await run(database, `INSERT INTO repair_suggestions (${COLUMNS.join(',')},generation) SELECT ${COLUMNS.join(',')},1 FROM repair_suggestions_before_versions`);
      await run(database, 'DROP TABLE repair_suggestions_before_versions');
      await run(database, 'COMMIT');
    } catch (error) {
      await run(database, 'ROLLBACK');
      throw error;
    }
  }
  await run(database, 'CREATE INDEX IF NOT EXISTS idx_repair_suggestions_finding ON repair_suggestions (job_id,document_id,rule_id,finding_id,generation DESC,created_at DESC)');
}
module.exports = { ensureArchiveRepairSchema };
