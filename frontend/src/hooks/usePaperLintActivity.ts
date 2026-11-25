import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPaperLintActivity, type PaperLintActivity } from '../api/paperLint';

export function usePaperLintActivity(owner: string | undefined) {
  const [state, setState] = useState<{ owner: string; activity: PaperLintActivity } | null>(null);
  const refreshRef = useRef<() => Promise<PaperLintActivity | null>>(async () => null);
  const refresh = useCallback(() => refreshRef.current(), []);
  useEffect(() => {
    if (!owner) { setState(null); refreshRef.current = async () => null; return; }
    let disposed = false, inFlight: Promise<PaperLintActivity | null> | null = null;
    let timer: ReturnType<typeof setTimeout>;
    const load = (): Promise<PaperLintActivity | null> => {
      if (disposed) return Promise.resolve(null);
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
          return disposed ? null : activity;
        } catch { return null; }
        finally { inFlight = null; if (!disposed) timer = setTimeout(() => void load(), delay); }
      })();
      return inFlight;
    };
    refreshRef.current = load;
    const reload = () => { void load(); };
    const visible = () => { if (document.visibilityState === 'visible') reload(); };
    void load(); window.addEventListener('focus', reload); document.addEventListener('visibilitychange', visible);
    return () => { disposed = true; clearTimeout(timer); refreshRef.current = async () => null; window.removeEventListener('focus', reload); document.removeEventListener('visibilitychange', visible); };
  }, [owner]);
  return { activity: state && state.owner === owner ? state.activity : null, refresh };
}
