import { beforeAll, afterAll, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { findingAnnotations, findingTarget } from '../../frontend/src/components/paperLint/geometry';

const require = createRequire(import.meta.url);
const repository = require('../src/normative/paperLintReportRepository');
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const harness = createTestDatabaseHarness({ label: 'paper-lint-evidence-locations' });
const python = process.env.PAPER_LINT_EVIDENCE_PYTHON || process.env.SIX_RULE_PYTHON || 'python3';
let directory, db, raw, originalPython;
const keywordQuote = 'FPGA, Operator Parallelism, Dataflow Architecture';
const abstractQuote = 'Our compiler uses program analysis, branch prediction, and automated scheduling.';

beforeAll(async () => {
  originalPython = process.env.PAPER_LINT_EVIDENCE_PYTHON;
  process.env.PAPER_LINT_EVIDENCE_PYTHON = python;
  directory = fs.mkdtempSync(path.join(os.tmpdir(), 'paper-lint-evidence-'));
  const pdf = path.join(directory, 'fixture.pdf');
  execFileSync(python, ['-c', [
    'import pymupdf,sys',
    'd=pymupdf.open(); p=d.new_page()',
    'p.insert_text((72,72),"Unrelated abstract text.")',
    'p.insert_text((72,140),"Key words: FPGA, Operator Parallelism,")',
    'p.insert_text((72,160),"Dataflow Architecture")',
    'p=d.new_page()',
    'p.insert_text((72,72),"Our compiler uses program analysis,")',
    'p.insert_text((72,112),"automated scheduling.")',
    'p.insert_text((72,132),"Unrelated next sentence.")',
    'p.insert_text((72,760),"IV")',
    'p.insert_text((72,92),"branch prediction, and")',
    'd.save(sys.argv[1])',
  ].join('\n'), pdf]);
  db = await harness.setup();
  await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('owner','owner','hash','STUDENT','COLLEGE')");
  const page = text => ({ type: 'pdf_page', page_number: 1, text_excerpt: text });
  const rule = (id, quote, excerpt, anchorId) => ({
    rule_id: id, severity: 'warning', execution_status: 'completed', outcome: 'issues_found',
    findings: [{ finding_id: id + '_1', rule_id: id, message: 'Existing finding classification and text.',
      suggestion: 'Existing suggestion.', location: page(excerpt),
      anchors: [{ anchor_id: anchorId, role: 'source_span', label: 'Existing label', location: page(excerpt) }],
      evidence: [{ id: anchorId, kind: 'source_span', provider: 'repo-paper-model', quote }],
    }],
  });
  raw = JSON.stringify({ type: 'paper_lint', rule_runs: [
    rule('bilingual_keywords_correspondence_check', keywordQuote, 'Key words: FPGA, Operator Parallelism,', 'keywords-2'),
    rule('bilingual_abstract_consistency_check', abstractQuote, abstractQuote, 'english_claim'),
  ], summary: { finding_count: 2 } });
  await db.run('INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES(?,?,?,?,?,?,?)',
    ['saved','owner','fixture.pdf',pdf,'[]',raw,new Date().toISOString()]);
});

afterAll(async () => {
  await harness.cleanup();
  if (directory) fs.rmSync(directory, { recursive: true, force: true });
  if (originalPython === undefined) delete process.env.PAPER_LINT_EVIDENCE_PYTHON;
  else process.env.PAPER_LINT_EVIDENCE_PYTHON = originalPython;
});

it('recovers old keyword and reinserted abstract evidence in responses without rewriting saved results', async () => {
  const detail = await repository.findPaperLintReportByIdForUser('saved', 'owner');
  const [keywords, abstract] = detail.result.rule_runs.map(run => run.findings[0]);
  expect(keywords.anchors[0].location.type).toBe('pdf_bbox');
  expect(keywords.anchors[0].location.rects).toHaveLength(2);
  expect(keywords.anchors[0].location.text_excerpt).toBe(keywordQuote);
  expect(keywords.anchors[0].location.rects.every(r => r.page_number === 1 && r.y1 > 120 && r.y2 < 170)).toBe(true);
  expect(abstract.anchors[0].location.type).toBe('pdf_bbox');
  expect(abstract.anchors[0].location.page_number).toBe(2);
  expect(abstract.anchors[0].location.rects).toHaveLength(3);
  expect(abstract.anchors[0].location.rects.every(r => r.page_number === 2 && r.y2 < 120)).toBe(true);
  expect(keywords.location).toEqual(keywords.anchors[0].location);
  expect(abstract.location).toEqual(abstract.anchors[0].location);
  for (const run of detail.result.rule_runs) {
    const finding = run.findings[0];
    const item = { key: finding.finding_id, index: 0, finding, ruleRun: run };
    const anchorId = finding.anchors[0].anchor_id;
    const target = findingTarget(item, anchorId);
    expect(target.type).toBe('bbox');
    expect(target.annotation.anchorId).toBe(anchorId);
    expect(findingAnnotations(item).some(annotation => annotation.anchorId === anchorId)).toBe(true);
  }
  for (const [index, run] of detail.result.rule_runs.entries()) {
    const saved = JSON.parse(raw).rule_runs[index];
    expect(run.severity).toBe(saved.severity);
    expect(run.outcome).toBe(saved.outcome);
    expect(run.findings[0].message).toBe(saved.findings[0].message);
    expect(run.findings[0].evidence).toEqual(saved.findings[0].evidence);
  }
  expect((await db.get('SELECT result_json FROM paper_lint_reports WHERE id=?', ['saved'])).result_json).toBe(raw);
  const [history] = await repository.listPaperLintReportsByUser('owner');
  expect(history).not.toHaveProperty('result');
  expect(history.summary).toEqual(detail.summary);
  expect(await repository.findPaperLintReportByIdForUser('saved', 'another-user')).toBeNull();
});

it('keeps saved detail readable when the PDF is unavailable', async () => {
  await db.run('UPDATE paper_lint_reports SET source_pdf_path=? WHERE id=?', [path.join(directory, 'missing.pdf'), 'saved']);
  const detail = await repository.findPaperLintReportByIdForUser('saved', 'owner');
  expect(detail.result.rule_runs[0].findings[0].anchors[0].location.type).toBe('pdf_page');
  expect((await db.get('SELECT result_json FROM paper_lint_reports WHERE id=?', ['saved'])).result_json).toBe(raw);
});

function locationResult(quote = 'A complete source sentence.') {
  return { rule_runs: [{ rule_id: 'bilingual_abstract_consistency_check', findings: [{
    location: { type: 'pdf_page', page_number: 1, text_excerpt: quote },
    anchors: [{ anchor_id: 'english_claim', role: 'source_span',
      location: { type: 'pdf_page', page_number: 1, text_excerpt: quote } }],
    evidence: [{ id: 'english_claim', kind: 'source_span', quote }],
  }] }] };
}
function geometry(queries, offset = 0) {
  return queries.map(query => {
    const rect = { x1: 20 + offset, y1: 80, x2: 120 + offset, y2: 92, width: 595, height: 842, page_number: 1 };
    return { type: 'pdf_bbox', page_number: 1, text_excerpt: query.quote, bounding_rect: rect, rects: [rect] };
  });
}

it('reuses bounded geometry cache, isolates response objects, and invalidates changed source or evidence', async () => {
  const { createEvidenceLocationService } = require('../src/normative/paperLintEvidenceLocations');
  const pdfPath = path.join(directory, 'cache-source.pdf');
  fs.writeFileSync(pdfPath, 'version one');
  let calls = 0;
  const service = createEvidenceLocationService({ maxEntries: 2,
    extract: async (_source, queries) => geometry(queries, ++calls) });
  const first = await service.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  expect(first.rule_runs[0].findings[0].location.bounding_rect.x1).toBe(21);
  first.rule_runs[0].findings[0].anchors[0].location.rects[0].x1 = 999;
  const repeat = await service.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  expect(repeat.rule_runs[0].findings[0].anchors[0].location.rects[0].x1).toBe(21);
  expect(calls).toBe(1);
  fs.appendFileSync(pdfPath, ' replaced');
  const replaced = await service.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  expect(replaced.rule_runs[0].findings[0].location.bounding_rect.x1).toBe(22);
  const different = await service.hydratePaperLintEvidenceLocations(locationResult('Different evidence.'), pdfPath);
  expect(different.rule_runs[0].findings[0].location.bounding_rect.x1).toBe(23);
  await service.hydratePaperLintEvidenceLocations(locationResult('Third evidence.'), pdfPath);
  const evicted = await service.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  expect(evicted.rule_runs[0].findings[0].location.bounding_rect.x1).toBe(25);
});

it('coalesces concurrent extraction and retries failures without blocking report reads', async () => {
  const { createEvidenceLocationService } = require('../src/normative/paperLintEvidenceLocations');
  const pdfPath = path.join(directory, 'concurrent-source.pdf');
  fs.writeFileSync(pdfPath, 'same source');
  let calls = 0, release;
  const gate = new Promise(resolve => { release = resolve; });
  const service = createEvidenceLocationService({ extract: async (_source, queries) => {
    calls += 1;
    await gate;
    return geometry(queries);
  } });
  const first = service.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  const second = service.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  release();
  for (const result of await Promise.all([first, second])) {
    expect(result.rule_runs[0].findings[0].location.type).toBe('pdf_bbox');
  }
  expect(calls).toBe(1);
  const retry = createEvidenceLocationService({ extract: async (_source, queries) => {
    if (++calls === 2) throw new Error('Unavailable runtime');
    return geometry(queries);
  } });
  const unavailable = await retry.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  expect(unavailable.rule_runs[0].findings[0].location.type).toBe('pdf_page');
  const recovered = await retry.hydratePaperLintEvidenceLocations(locationResult(), pdfPath);
  expect(recovered.rule_runs[0].findings[0].location.type).toBe('pdf_bbox');
});

it('leaves unrelated rules, existing rectangles, and absent or ambiguous evidence unchanged', async () => {
  const { createEvidenceLocationService } = require('../src/normative/paperLintEvidenceLocations');
  let calls = 0;
  const service = createEvidenceLocationService({ extract: async (_source, queries) => {
    calls += 1;
    return queries.map(() => null);
  } });
  const pdfPath = path.join(directory, 'no-evidence-source.pdf');
  fs.writeFileSync(pdfPath, 'same source');
  const unrelated = locationResult();
  unrelated.rule_runs[0].rule_id = 'unrelated_rule';
  const before = JSON.stringify(unrelated);
  await service.hydratePaperLintEvidenceLocations(unrelated, pdfPath);
  expect(JSON.stringify(unrelated)).toBe(before);
  expect(calls).toBe(0);
  const precise = locationResult();
  precise.rule_runs[0].findings[0].anchors[0].location = geometry([{ quote: 'Precise source.' }])[0];
  const original = JSON.stringify(precise);
  await service.hydratePaperLintEvidenceLocations(precise, pdfPath);
  expect(JSON.stringify(precise)).toBe(original);
  expect(calls).toBe(0);
  const absent = locationResult();
  const saved = JSON.stringify(absent);
  await service.hydratePaperLintEvidenceLocations(absent, pdfPath);
  expect(JSON.stringify(absent)).toBe(saved);
  expect(calls).toBe(1);
});

it('keeps historical page-only evidence readable when the optional Python runtime is unavailable', async () => {
  const { createEvidenceLocationService } = require('../src/normative/paperLintEvidenceLocations');
  const service = createEvidenceLocationService();
  const result = locationResult();
  const original = JSON.stringify(result);
  const savedPython = process.env.PAPER_LINT_EVIDENCE_PYTHON;
  process.env.PAPER_LINT_EVIDENCE_PYTHON = path.join(directory, 'missing-python');
  try {
    await service.hydratePaperLintEvidenceLocations(result, path.join(directory, 'fixture.pdf'));
    expect(JSON.stringify(result)).toBe(original);
  } finally {
    process.env.PAPER_LINT_EVIDENCE_PYTHON = savedPython;
  }
});
