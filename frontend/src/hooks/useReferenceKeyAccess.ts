import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchReferenceSettings } from '../api/referenceSettings';

export const REFERENCE_RULE_ID = 'reference_verification_check';
export type ReferenceKeyAccess = { ready: boolean; loading: boolean; error: boolean };

/** Eligibility, including local-account exceptions, is decided by the server. */
export function useReferenceKeyAccess(owner: string | undefined, enabled: boolean) {
  const [state, setState] = useState<(ReferenceKeyAccess & { owner: string }) | null>(null);
  const refreshRef = useRef<() => Promise<boolean>>(async () => false);
  const refresh = useCallback(() => refreshRef.current(), []);
  useEffect(() => {
    if (!owner || !enabled) { setState(null); return; }
    let disposed = false;
    let controller: AbortController | null = null;
    let generation = 0;
    const load = async () => {
      const current = ++generation;
      controller?.abort();
      controller = new AbortController();
      setState({ owner, ready: false, loading: true, error: false });
      try {
        const status = await fetchReferenceSettings(controller.signal);
        if (disposed || generation !== current) return false;
        const ready = status.can_verify_references === true;
        setState({ owner, ready, loading: false, error: false });
        return ready;
      } catch {
        if (!disposed && generation === current) setState({ owner, ready: false, loading: false, error: true });
        return false;
      }
    };
    refreshRef.current = load;
    const reload = () => { void load(); };
    const visible = () => { if (document.visibilityState === 'visible') reload(); };
    void load();
    window.addEventListener('smart-degree:reference-settings-changed', reload);
    window.addEventListener('focus', reload);
    document.addEventListener('visibilitychange', visible);
    return () => {
      disposed = true; controller?.abort(); refreshRef.current = async () => false;
      window.removeEventListener('smart-degree:reference-settings-changed', reload);
      window.removeEventListener('focus', reload);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [owner, enabled]);
  const current = enabled && state?.owner === owner ? state : null;
  return { ready: current?.ready ?? false, loading: current?.loading ?? enabled, error: current?.error ?? false, refresh };
}
