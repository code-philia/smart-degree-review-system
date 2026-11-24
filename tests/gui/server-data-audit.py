"""Operator helper for this GUI run only; no application code/config changes.

snapshot: hash existing rows in a private server file.
cleanup: remove only registry-confirmed GUI_TEST data, then verify old rows.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

if sys.flags.optimize:
    raise RuntimeError('Run this scoped cleanup without Python -O; safety assertions must remain enabled')

action, task_path = sys.argv[1:3]
task = Path(task_path)
task.mkdir(mode=0o700, parents=True, exist_ok=True)
pid = subprocess.check_output(['systemctl', 'show', 'smart-degree.service', '-p', 'MainPID', '--value'], text=True).strip()
env = dict(v.split('=', 1) for v in Path('/proc', pid, 'environ').read_text().split('\0') if '=' in v)
database = Path(env.get('ARC_DB_FILE') or env['DATABASE_FILE'])
backend = Path('/proc', pid, 'cwd').resolve()
tables = ['auth_users', 'paper_lint_reports', 'normative_detection_tasks', 'duplication_detection_reports', 'example_rule_reports', 'system_feedback',
          'paper_lint_finding_feedback', 'paper_lint_suggestion_feedback', 'paper_lint_jobs', 'paper_lint_credit_accounts', 'paper_lint_credit_calls',
          'user_announcement_receipts', 'user_notification_reads', 'report_email_outbox', 'paper_lint_credit_operations', 'paper_lint_repair_suggestions']

def snapshot():
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('BEGIN')
        present = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {table: {str(row[0]): hashlib.sha256(json.dumps(row[1:], ensure_ascii=False, default=str, separators=(',', ':')).encode()).hexdigest()
                        for row in db.execute('SELECT rowid,* FROM ' + table)} for table in tables if table in present}

if action == 'extend-baseline':
    target = task / 'baseline.json'
    old = json.loads(target.read_text())
    additions = {table: rows for table, rows in snapshot().items() if table not in old}
    (task / 'baseline-original.json').write_text(json.dumps(old))
    (task / 'baseline-original.json').chmod(0o600)
    target.write_text(json.dumps({**old, **additions}))
    print(json.dumps({'original_baseline_preserved': True, 'additional_tables_before_mutation': sorted(additions)}))
elif action == 'snapshot':
    target = task / 'baseline.json'
    assert not target.exists(), 'Refuse to replace the original data baseline'
    target.write_text(json.dumps(snapshot()))
    target.chmod(0o600)
    print(json.dumps({'baseline_saved': True, 'table_count': len(snapshot()), 'production_code_unchanged': True}))
elif action == 'cleanup':
    baseline = json.loads((task / 'baseline.json').read_text())
    run = json.loads((task / 'run.json').read_text())
    prefix = run['prefix']
    assert prefix.startswith('GUI_TEST_') and len(prefix) > 25
    events = [json.loads(line) for line in (task / 'created.jsonl').read_text().splitlines() if line.strip()]
    job_ids = {e['id'] for e in events if e['kind'] == 'job'}
    request_ids = {e['request_id'] for e in events if e['kind'] == 'request' and e.get('request_id')}
    feedback_ids = {e['id'] for e in events if e['kind'] == 'system-feedback'}
    report_ids = {e['id'] for e in events if e['kind'] == 'report'}
    files = []
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        jobs = db.execute('SELECT rowid,id,user_id,source_filename,source_pdf_path,status,cancelled_at,report_id,request_id FROM paper_lint_jobs WHERE user_id=? AND source_filename LIKE ?', ['student01', prefix + '%']).fetchall()
        for rowid, jid, uid, filename, filename_path, status, cancelled, rid, request_id in jobs:
            assert jid in job_ids or request_id in request_ids, 'Unregistered test job'
            assert str(rowid) not in baseline['paper_lint_jobs'] and filename.startswith(prefix)
            assert status in ('completed', 'failed') or cancelled, 'Test worker is still active'
            if rid:
                assert rid in report_ids, 'Report ID not reconciled by browser cleanup'
                assert not db.execute('SELECT 1 FROM paper_lint_reports WHERE id=?', [rid]).fetchone(), 'Use report API cleanup first'
            source = Path(filename_path)
            expected_root = Path(env.get('PAPER_LINT_JOBS_DIR') or backend / 'data/paper-lint-jobs').resolve()
            assert source.resolve().parent == expected_root and source.name == jid + '.pdf'
            files.append(source)
            db.execute('DELETE FROM paper_lint_jobs WHERE id=? AND user_id=?', [jid, 'student01'])
        for fid in feedback_ids:
            row = db.execute('SELECT rowid,user_id,comment FROM system_feedback WHERE id=?', [fid]).fetchone()
            if row:
                assert str(row[0]) not in baseline['system_feedback'] and row[1] == 'student01' and row[2].startswith(prefix)
                db.execute('DELETE FROM system_feedback WHERE id=? AND user_id=?', [fid, 'student01'])
        db.commit()
    for file in files:
        file.unlink(missing_ok=True)
        file.with_name(file.name + '.metrics.json').unlink(missing_ok=True)
        file.with_name(file.name + '.browser-cache').unlink(missing_ok=True)
    archive_verified = not feedback_ids
    if feedback_ids:
        # Read-only adapter avoids the application's global schema/account initialization.
        # Use the strict refresh API: archive write failures must fail this cleanup.
        script = '''const sqlite3=require('sqlite3');
const file=process.argv[1];
const connection=new sqlite3.Database(file,sqlite3.OPEN_READONLY);
const database={all:sql=>new Promise((resolve,reject)=>connection.all(sql,[],(e,r)=>e?reject(e):resolve(r)))};
(async()=>{try{await require('./src/normative/feedbackArchive').refreshFeedbackArchive({database,dbPath:file});}
finally{await new Promise((resolve,reject)=>connection.close(e=>e?reject(e):resolve()));}})()
.catch(e=>{console.error(e.name);process.exit(1)});'''
        subprocess.run(['/data/envs/smartdegree-node-v22.23.2/bin/node', '-e', script, str(database)], cwd=backend, env=env, check=True, capture_output=True)
        archive_dir = database.parent / 'feedback'
        archive_json = (archive_dir / 'feedback.json').read_text()
        archive_csv = (archive_dir / 'feedback.csv').read_text()
        records = json.loads(archive_json)['records']
        assert prefix not in archive_json and prefix not in archive_csv, 'Marked feedback remains in derived archive'
        assert not feedback_ids.intersection(r['id'] for r in records), 'Registered feedback remains in JSON archive'
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            expected_feedback = {row[0] for table in ['system_feedback', 'paper_lint_finding_feedback', 'paper_lint_suggestion_feedback'] for row in db.execute('SELECT id FROM ' + table)}
        assert {r['id'] for r in records} == expected_feedback, 'Derived archive is not synchronized with saved feedback'
        archive_verified = True
    after = snapshot()
    changed = {table: [rid for rid, digest in rows.items() if after[table].get(rid) != digest] for table, rows in baseline.items()}
    changed = {table: ids for table, ids in changed.items() if ids}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        leftovers = {table: db.execute('SELECT count(*) FROM ' + table + ' WHERE user_id=? AND ' + field + ' LIKE ?', ['student01', prefix + '%']).fetchone()[0]
                     for table, field in [('paper_lint_jobs', 'source_filename'), ('paper_lint_reports', 'source_filename'), ('system_feedback', 'comment')]}
    result = {'test_jobs_removed': len(files), 'test_system_feedback_ids': sorted(feedback_ids), 'existing_rows_changed': changed,
              'derived_feedback_archive_verified': archive_verified,
              'test_data_leftovers': leftovers, 'no_marked_data_left': not any(leftovers.values()),
              'all_existing_rows_preserved': not changed, 'after_counts': {t: len(v) for t, v in after.items()}}
    (task / 'cleanup-verified.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    assert not changed, 'Existing rows changed; inspect private baseline and concurrent-user activity before attributing changes'
    assert not any(leftovers.values()), 'Marked test data remains; do not delete unregistered records without reconciliation'
else:
    raise ValueError('Unknown audit action')
