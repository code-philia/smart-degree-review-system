const path = require('node:path');
const fs = require('node:fs');
const ROOT = path.resolve(__dirname, '../..');
const OUT = path.resolve(process.env.GUI_OUTPUT_DIR || path.join(ROOT, 'output/campus-gui-20261125'));
const BASE = process.env.GUI_BASE_URL || 'https://thesis-review.sjtu.edu.cn';
const target = new URL(BASE);
const deployed = ['https://thesis-review.sjtu.edu.cn', 'http://121.36.247.138:3000'].includes(target.origin);
const localPreview = process.env.GUI_ALLOW_LOCAL === '1' && target.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(target.hostname);
if (!deployed && !localPreview) throw new Error('GUI audit target must be a deployed site or an explicitly enabled loopback preview');
fs.mkdirSync(OUT, { recursive: true });
const MANIFEST = path.join(OUT, 'facts.json');
const RUN = path.join(OUT, 'run.json');
const REGISTRY = path.join(OUT, 'created.jsonl');
const PDF_FIXTURE = path.join(ROOT, 'backend/tests/fixtures/local-four-rule-sample.pdf');
const LIVE_PDF = process.env.GUI_LIVE_PDF ? path.resolve(process.env.GUI_LIVE_PDF) : null;
const state = role => path.join(OUT, '.auth', role + '.json');
function facts() { return JSON.parse(fs.readFileSync(MANIFEST, 'utf8')); }
function run() { return JSON.parse(fs.readFileSync(RUN, 'utf8')); }
function created() { return fs.existsSync(REGISTRY) ? fs.readFileSync(REGISTRY, 'utf8').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line)) : []; }
function record(value) { fs.appendFileSync(REGISTRY, JSON.stringify({ ...value, at: new Date().toISOString() }) + '\n'); }
module.exports = { ROOT, OUT, BASE, MANIFEST, RUN, REGISTRY, PDF_FIXTURE, LIVE_PDF, state, facts, run, created, record };
