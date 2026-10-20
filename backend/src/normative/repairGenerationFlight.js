const inFlight = new Map();
async function shareRepairGeneration(key, work) {
  if (inFlight.has(key)) return inFlight.get(key);
  const pending = Promise.resolve().then(work);
  inFlight.set(key, pending);
  try { return await pending; }
  finally { if (inFlight.get(key) === pending) inFlight.delete(key); }
}
module.exports = { shareRepairGeneration };
