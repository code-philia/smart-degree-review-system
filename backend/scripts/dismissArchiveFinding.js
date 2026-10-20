// Operator command for a user-confirmed false positive. Take an online DB backup
// first, then run with ARC_DB_FILE set and a private JSON review manifest as argv[2].
const fs = require('fs');
const { createHash } = require('crypto');
const db = require('../src/database/db_runtime');

async function dismissArchiveFinding({ jobId, documentId, ruleId, findingId, expectedResultSha256, reason }) {
  if (![jobId, documentId, ruleId, findingId, reason].every(value => typeof value === 'string' && value.trim()) ||
      !/^[a-f0-9]{64}$/.test(expectedResultSha256 || '')) {
    throw new Error('A precise finding identity, source SHA-256 and review reason are required');
  }
  return db.withTransaction(async tx => {
    const row = await tx.get('SELECT * FROM archive_scan_documents WHERE job_id=? AND id=?', [jobId, documentId]);
    if (!row) throw new Error('Archive document not found');
    const job = await tx.get('SELECT status FROM archive_scan_jobs WHERE id=?', [jobId]);
    if (row.status !== 'completed' || job?.status !== 'completed') throw new Error('Only completed results can be reviewed');
    const result = JSON.parse(row.result_json);
    const reviews = result.finding_reviews || [];
    if (reviews.some(review => review.rule_id === ruleId && review.finding_id === findingId && review.disposition === 'false_positive')) {
      return { changed: false, jobId, documentId, ruleId, findingId };
    }
    if (createHash('sha256').update(row.result_json).digest('hex') !== expectedResultSha256) {
      throw new Error('Stored result changed; review the current result before retrying');
    }
    const runs = result.rule_runs.filter(run => run.rule_id === ruleId);
    if (runs.length !== 1) throw new Error('Expected exactly one matching rule run');
    const run = runs[0];
    const matches = run.findings.filter(finding => finding.finding_id === findingId);
    if (matches.length !== 1) throw new Error('Expected exactly one matching finding');
    if (run.execution_status !== 'completed') throw new Error('The selected rule has not completed');
    const originalFinding = matches[0];
    run.findings = run.findings.filter(finding => finding.finding_id !== findingId);
    if (!run.findings.length && run.outcome === 'issues_found') {
      run.outcome = 'passed';
      if (run.publication_status === 'ALERT') run.publication_status = 'NO_ALERT';
    }
    result.finding_reviews = [...reviews, {
      rule_id: ruleId, finding_id: findingId, disposition: 'false_positive',
      reason: reason.trim(), reviewed_at: new Date().toISOString(),
      original_result_sha256: expectedResultSha256, original_finding: originalFinding,
    }];
    const total = result.rule_runs.reduce((sum, item) => sum + item.findings.length, 0);
    result.summary = {
      ...result.summary,
      finding_count: total,
      issue_rule_count: result.rule_runs.filter(item => item.findings.length > 0).length,
      ...Object.fromEntries(['error', 'warning', 'info'].map(severity => [
        severity + '_finding_count',
        result.rule_runs.filter(item => item.severity === severity).reduce((sum, item) => sum + item.findings.length, 0),
      ])),
    };
    const outcomes = JSON.parse(row.rule_outcomes_json || '{}');
    outcomes[ruleId] = run.publication_status === 'NO_ALERT' ? 'no_alert' : run.outcome;
    await tx.run('UPDATE archive_scan_documents SET result_json=?, rule_outcomes_json=?, finding_count=? WHERE job_id=? AND id=?',
      [JSON.stringify(result), JSON.stringify(outcomes), total, jobId, documentId]);
    await tx.run('UPDATE archive_scan_jobs SET finding_count=(SELECT COALESCE(SUM(finding_count),0) FROM archive_scan_documents WHERE job_id=?) WHERE id=?',
      [jobId, jobId]);
    return { changed: true, jobId, documentId, ruleId, findingId, findingCount: total };
  });
}
module.exports = { dismissArchiveFinding };
if (require.main === module) {
  (async () => {
    try {
      if (process.argv.length !== 3) throw new Error('Usage: node scripts/dismissArchiveFinding.js /private/review.json');
      const review = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
      console.log(JSON.stringify(await dismissArchiveFinding(review)));
    } catch (error) {
      console.error(error.message);
      process.exitCode = 1;
    } finally {
      await require('../src/database/init_db').closeDb();
    }
  })();
}
