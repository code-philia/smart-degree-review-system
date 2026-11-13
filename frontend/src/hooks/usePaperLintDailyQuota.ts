import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPaperLintDailyQuota, type PaperLintDailyQuota } from '../api/paperLint';

/** Server-authoritative allowance, refreshed on task changes, focus and cross-tab updates. */
export function usePaperLintDailyQuota(ownerKey: string | null | undefined, refreshKey?: unknown) {
  const [state, setState] = useState<{owner: string; quota: PaperLintDailyQuota | null; error: boolean} | null>(null);
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  const refresh = useCallback(() => refreshRef.current(), []);
  useEffect(() => {
    if (!ownerKey) { setState(null); refreshRef.current = async () => {}; return; }
    let disposed = false, sequence = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      const request = ++sequence;
      try {
        const quota = await fetchPaperLintDailyQuota();
        if (disposed || request !== sequence) return;
        setState({owner: ownerKey!, quota, error: false});
        clearTimeout(timer);
      } catch {
        if (disposed || request !== sequence) return;
        setState(previous => ({owner: ownerKey!, quota: previous?.owner === ownerKey ? previous.quota : null, error: true}));
        clearTimeout(timer);
        timer = setTimeout(() => void load(), 30_000);
      }
    }
    const focus = () => { void load(); };
    const visible = () => { if (document.visibilityState === 'visible') void load(); };
    const storage = (event: StorageEvent) => {
      if (!event.key || /^(paper-lint|numeric-review)-active-job:/.test(event.key)) void load();
    };
    refreshRef.current = load;
    void load();
    window.addEventListener('focus', focus);
    window.addEventListener('storage', storage);
    document.addEventListener('visibilitychange', visible);
    return () => {
      disposed = true; clearTimeout(timer);
      window.removeEventListener('focus', focus);
      window.removeEventListener('storage', storage);
      document.removeEventListener('visibilitychange', visible);
      refreshRef.current = async () => {};
    };
  }, [ownerKey, refreshKey]);
  const current = state?.owner === ownerKey ? state : null;
  return {quota: current?.quota ?? null, error: current?.error ?? false, refresh};
}
