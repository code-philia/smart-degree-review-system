import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPaperLintActivity, type PaperLintActivity } from '../api/paperLint';

export function usePaperLintActivity(owner: string | undefined) {
  const [state, setState] = useState<{ owner: string; activity: PaperLintActivity } | null>(null);
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  const refresh = useCallback(() => refreshRef.current(), []);
  useEffect(() => {
    if (!owner) { setState(null); refreshRef.current = async () => {}; return; }
    let disposed = false, inFlight: Promise<void> | null = null;
    let timer: ReturnType<typeof setTimeout>;
    const load = (): Promise<void> => {
      if (disposed) return Promise.resolve();
      if (inFlight) return inFlight;
      clearTimeout(timer);
      inFlight = (async () => {
        let delay = 10000;
        try {
          const activity = await fetchPaperLintActivity();
          if (activity.user_id !== owner || (activity.active_job && activity.active_job.user_id !== owner)) {
            throw new Error('Activity account changed');
          }
          if (!disposed) setState({ owner, activity });
          delay = activity.busy ? 1500 : 5000;
        } catch { /* The server still enforces admission if a status refresh fails. */ }
        finally { inFlight = null; if (!disposed) timer = setTimeout(() => void load(), delay); }
      })();
      return inFlight;
    };
    refreshRef.current = load;
    const reload = () => { void load(); };
    const visible = () => { if (document.visibilityState === 'visible') reload(); };
    void load(); window.addEventListener('focus', reload); document.addEventListener('visibilitychange', visible);
    return () => { disposed = true; clearTimeout(timer); refreshRef.current = async () => {}; window.removeEventListener('focus', reload); document.removeEventListener('visibilitychange', visible); };
  }, [owner]);
  return { activity: state?.owner === owner ? state.activity : null, refresh };
}
