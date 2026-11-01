const fs = require('fs/promises');
const { execFile } = require('child_process');
const { promisify } = require('util');
const { randomUUID } = require('crypto');

const execute = promisify(execFile);
const pending = new Map();
const waiters = [];
let active = 0;
// Keep browser copies out of archive discovery, which enumerates *.pdf files.
const browserPdfPath = source => `${source}.browser-cache`;

async function linearized(file) {
  const handle = await fs.open(file, 'r');
  try {
    const buffer = Buffer.alloc(2048);
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    return buffer.subarray(0, bytesRead).includes(Buffer.from('/Linearized'));
  } finally { await handle.close(); }
}

async function optimize(source) {
  const original = await fs.stat(source);
  if (await linearized(source)) return source;
  const output = browserPdfPath(source);
  const cached = await fs.stat(output).catch(() => null);
  if (cached?.size > 0 && cached.mtimeMs >= original.mtimeMs) return output;

  // Bound PDF processing across concurrent readers, and share work per source.
  if (active >= 2) await new Promise(resolve => waiters.push(resolve));
  else active++;
  const temporary = `${output}.${randomUUID()}.tmp`;
  try {
    await fs.writeFile(temporary, '', { flag: 'wx', mode: 0o600 });
    await execute(process.env.ARC_QPDF_BINARY || 'qpdf',
      ['--warning-exit-0', '--linearize', '--object-streams=generate', source, temporary],
      { timeout: 15_000, maxBuffer: 256 * 1024 });
    if (!(await linearized(temporary))) return source;
    const latest = await fs.stat(source);
    if (latest.size !== original.size || latest.mtimeMs !== original.mtimeMs) return source;
    await fs.chmod(temporary, 0o600);
    await fs.rename(temporary, output);
    return output;
  } finally {
    await fs.rm(temporary, { force: true }).catch(() => {});
    const next = waiters.shift();
    if (next) next();
    else active--;
  }
}

function prepareBrowserPdf(source) {
  if (!pending.has(source)) {
    // A missing tool or malformed input must never prevent access to the PDF.
    pending.set(source, optimize(source).catch(() => source).finally(() => pending.delete(source)));
  }
  return pending.get(source);
}

async function removeBrowserPdf(source) {
  await pending.get(source);
  await fs.rm(browserPdfPath(source), { force: true });
}

module.exports = { browserPdfPath, prepareBrowserPdf, removeBrowserPdf };
