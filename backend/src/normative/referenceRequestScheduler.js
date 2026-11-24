// One public Crossref connection per process. Tests/private callers may inject
// a separate governor, while all ordinary jobs share the exported singleton.
function cancelled() { return Object.assign(new Error('Reference verification cancelled'), { name: 'AbortError' }); }
function pause(ms, signal) {
  if (signal?.aborted) return Promise.reject(cancelled());
  return new Promise((resolve, reject) => {
    const finish = () => { signal?.removeEventListener('abort', abort); resolve(); };
    const timer = setTimeout(finish, ms);
    const abort = () => { clearTimeout(timer); signal?.removeEventListener('abort', abort); reject(cancelled()); };
    signal?.addEventListener('abort', abort, { once: true });
  });
}
function createCrossrefScheduler() {
  const queue = [];
  let busy = false, nextAt = 0, blockedUntil = 0;
  async function drain() {
    if (busy) return;
    busy = true;
    try {
      while (queue.length) {
        const task = queue.shift();
        try {
          if (task.signal?.aborted) throw cancelled();
          // A long provider backoff is reported truthfully; it must not turn
          // every newly submitted entry into minutes of unbounded retry sleep.
          if (blockedUntil - Date.now() > 5000) { task.resolve({ status: 'rate_limited' }); continue; }
          while (Math.max(nextAt, blockedUntil) > Date.now()) {
            await pause(Math.max(nextAt, blockedUntil) - Date.now(), task.signal);
          }
          if (task.signal?.aborted) throw cancelled();
          nextAt = Date.now() + task.interval;
          task.started = true;
          task.resolve(await task.operation(Date.now() - task.enqueuedAt));
        } catch (error) { task.reject(error); }
        finally { task.signal?.removeEventListener('abort', task.abort); }
      }
    } finally { busy = false; }
  }
  return {
    defer(ms) { blockedUntil = Math.max(blockedUntil, Date.now() + ms); },
    run(operation, { signal, interval }) {
      if (signal?.aborted) return Promise.reject(cancelled());
      return new Promise((resolve, reject) => {
        const task = { operation, signal, interval, resolve, reject, enqueuedAt: Date.now(), started: false };
        task.abort = () => {
          if (task.started) return;
          const index = queue.indexOf(task);
          if (index >= 0) { queue.splice(index, 1); signal.removeEventListener('abort', task.abort); reject(cancelled()); }
        };
        signal?.addEventListener('abort', task.abort, { once: true });
        queue.push(task);
        queueMicrotask(() => { void drain(); });
      });
    },
  };
}
module.exports = { createCrossrefScheduler, crossrefScheduler: createCrossrefScheduler() };
