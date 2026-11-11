// In-process fast path only. The durable outbox and fallback scan handle restarts.
const listeners=new Set();
function notifyReportEmailReady() {
  queueMicrotask(()=>{
    for (const listener of [...listeners]) {
      try {listener();} catch {console.error('Report email wake-up temporarily unavailable');}
    }
  });
}
function onReportEmailReady(listener) {
  listeners.add(listener);
  return ()=>listeners.delete(listener);
}
module.exports={notifyReportEmailReady,onReportEmailReady};
