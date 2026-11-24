// Independent instances keep administrator attempts out of the trial-login budget.
function createLoginAttempts() {
  const attempts = new Map();
  let nextCleanup = 0;
  const windowMs = 15 * 60 * 1000;
  return {
    clear() { attempts.clear(); nextCleanup = 0; },
    consume(req) {
      const now = Date.now();
      if (now >= nextCleanup) {
        for (const [key, value] of attempts) if (value.until <= now) attempts.delete(key);
        nextCleanup = now + 60_000;
      }
      const peer = req.socket?.remoteAddress || 'unknown';
      const username = typeof req.body?.username === 'string' ? req.body.username.slice(0, 128) : '';
      const buckets = [[`ip:${peer}`, 20], [`account:${peer}:${username}`, 5]];
      for (const [key, limit] of buckets) {
        const value = attempts.get(key);
        if (value?.until > now && value.count >= limit) return Math.ceil((value.until - now) / 1000);
        if (!value && attempts.size >= 10_000) return 60;
      }
      for (const [key] of buckets) {
        let value = attempts.get(key);
        if (!value || value.until <= now) { value = { count: 0, until: now + windowMs }; attempts.set(key, value); }
        value.count++;
      }
      return 0;
    },
  };
}
module.exports = { createLoginAttempts };
