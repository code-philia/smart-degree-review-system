const inFlight = new Map();
const queue = [];
let active = 0;
let lastStarted = 0;
const MAX_CONCURRENT = 2;
const MIN_INTERVAL_MS = Math.max(0, Number(process.env.SJTU_API_MIN_REQUEST_INTERVAL_MS || 6000));

function pump() {
  if (active >= MAX_CONCURRENT || queue.length === 0) return;
  const wait = Math.max(0, MIN_INTERVAL_MS - (Date.now() - lastStarted));
  if (wait) return void setTimeout(pump, wait);
  const item = queue.shift();
  active += 1;
  lastStarted = Date.now();
  Promise.resolve().then(item.work).then(item.resolve, item.reject).finally(() => {
    active -= 1;
    pump();
  });
}

function enqueue(work) {
  return new Promise((resolve, reject) => {
    queue.push({ work, resolve, reject });
    pump();
  });
}

async function shareRepairGeneration(key, work) {
  if (inFlight.has(key)) return inFlight.get(key);
  const pending = enqueue(work);
  inFlight.set(key, pending);
  try { return await pending; }
  finally { if (inFlight.get(key) === pending) inFlight.delete(key); }
}
module.exports = { shareRepairGeneration };
