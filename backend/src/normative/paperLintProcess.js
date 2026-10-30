const { spawn } = require('child_process');

function runPaperLintProcess(command, args, { signal, timeoutMs, maxBytes, env = process.env }) {
  if (signal?.aborted) return Promise.reject(Object.assign(new Error('Cancelled'), { name: 'AbortError' }));
  return new Promise((resolve, reject) => {
    const posix = process.platform !== 'win32';
    const child = spawn(command, args, { detached: posix, windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'], env });
    const chunks = { stdout: [], stderr: [] };
    const bytes = { stdout: 0, stderr: 0 };
    let failure;
    function stop() {
      if (!child.pid) return;
      try { if (posix) process.kill(-child.pid, 'SIGKILL'); else child.kill('SIGKILL'); }
      catch (error) { if (error.code !== 'ESRCH') failure ||= error; }
    }
    function abort() { failure ||= Object.assign(new Error('Cancelled'), { name: 'AbortError' }); stop(); }
    const timer = setTimeout(() => { failure ||= Object.assign(new Error('Timed out'), { killed: true }); stop(); }, timeoutMs);
    for (const stream of ['stdout', 'stderr']) {
      child[stream].on('data', chunk => {
        bytes[stream] += chunk.length;
        if (bytes[stream] > maxBytes) {
          failure ||= Object.assign(new Error('Output limit'), { code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' });
          stop();
        } else chunks[stream].push(chunk);
      });
    }
    child.once('error', error => { failure ||= error; });
    // Workers share the new process group. Clean up descendants even when their
    // leader exits first, and settle only after process stdio has closed.
    child.once('exit', stop);
    child.once('close', (code, exitSignal) => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      const output = Object.fromEntries(Object.entries(chunks).map(([key, value]) => [key, Buffer.concat(value).toString('utf8')]));
      if (!failure && code !== 0) failure = Object.assign(new Error('Process failed'), { code, signal: exitSignal });
      if (failure) reject(Object.assign(failure, output)); else resolve(output);
    });
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
  });
}

module.exports = { runPaperLintProcess };
