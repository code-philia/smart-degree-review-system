const { randomUUID } = require('crypto');
const { all, get, run } = require('../database');

function parseCorpusRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    title: row.title,
    subject: row.subject,
    year: row.year,
    content: row.content,
    source_type: row.source_type,
    source_filename: row.source_filename || null,
    created_by: row.created_by,
    created_at: row.created_at,
  };
}

async function createCorpusSample(sample) {
  const id = sample.id || randomUUID();
  const createdAt = sample.created_at || new Date().toISOString();

  await run(
    `INSERT INTO duplication_corpus_samples (
      id,
      title,
      subject,
      year,
      content,
      source_type,
      source_filename,
      created_by,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);`,
    [
      id,
      sample.title,
      sample.subject,
      sample.year,
      sample.content,
      sample.source_type,
      sample.source_filename || null,
      sample.created_by,
      createdAt,
    ],
  );

  return {
    id,
    title: sample.title,
    subject: sample.subject,
    year: sample.year,
    content: sample.content,
    source_type: sample.source_type,
    source_filename: sample.source_filename || null,
    created_by: sample.created_by,
    created_at: createdAt,
  };
}

async function listCorpusSamples() {
  const rows = await all(
    `SELECT *
     FROM duplication_corpus_samples
     ORDER BY created_at DESC;`,
  );
  return rows.map(parseCorpusRow);
}

async function deleteCorpusSample(sampleId) {
  const existing = await get('SELECT id FROM duplication_corpus_samples WHERE id = ?;', [sampleId]);
  if (!existing) {
    return false;
  }
  await run('DELETE FROM duplication_corpus_samples WHERE id = ?;', [sampleId]);
  return true;
}

module.exports = {
  createCorpusSample,
  deleteCorpusSample,
  listCorpusSamples,
  parseCorpusRow,
};
