import { useEffect, useRef, useState } from 'react';

type MotionPreference = 'auto' | 'on' | 'off';
const storageKey = 'smartdegree:auth-campus-motion';

function readPreference(): MotionPreference {
  try {
    const saved = localStorage.getItem(storageKey);
    return saved === 'on' || saved === 'off' ? saved : 'auto';
  } catch {
    return 'auto';
  }
}

export default function useAuthCampusScene() {
  const imageRef = useRef<HTMLImageElement>(null);
  const motionRef = useRef<HTMLDivElement>(null);
  const [preference, setPreference] = useState<MotionPreference>(readPreference);
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );
  const enabled = preference === 'on' || (preference === 'auto' && !reduced);

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const changed = () => setReduced(query?.matches ?? false);
    query?.addEventListener?.('change', changed);
    const stored = (event: StorageEvent) => {
      if (event.key === storageKey) setPreference(readPreference());
    };
    window.addEventListener('storage', stored);
    return () => {
      query?.removeEventListener?.('change', changed);
      window.removeEventListener('storage', stored);
    };
  }, []);

  useEffect(() => {
    function arrange() {
      const image = imageRef.current;
      if (!image) return;
      const width = window.innerWidth;
      const height = window.innerHeight;
      const target = {
        x: width * (width <= 950 ? 0.5 : 0.43),
        y: width <= 950 ? Math.min(480, height - 120) : height * 0.4,
      };
      const center = { x: 1056.5, y: 506 };
      // An eight-pixel edge reserve covers all allowed pointer movement without extra zoom.
      const scale = Math.max(
        (width + 16) / 2048,
        (height + 16) / 1397,
        (target.x + 8) / center.x,
        (width - target.x + 8) / (2048 - center.x),
        (target.y + 8) / center.y,
        (height - target.y + 8) / (1397 - center.y),
      );
      Object.assign(image.style, {
        width: `${2048 * scale}px`,
        height: `${1397 * scale}px`,
        left: `${target.x - center.x * scale}px`,
        top: `${target.y - center.y * scale}px`,
      });
      if (motionRef.current) motionRef.current.style.transform = 'none';
    }
    arrange();
    window.addEventListener('resize', arrange);
    return () => window.removeEventListener('resize', arrange);
  }, []);

  useEffect(() => {
    const layer = motionRef.current;
    if (!layer) return;
    layer.style.transform = 'none';
    const pointer = window.matchMedia?.('(hover: hover) and (pointer: fine)');
    if (!enabled || !pointer?.matches) return;
    let frame = 0;
    let point = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    function reset() {
      cancelAnimationFrame(frame);
      frame = 0;
      layer!.style.transform = 'none';
    }
    function move(event: PointerEvent) {
      if (event.pointerType !== 'mouse') return;
      if (document.activeElement instanceof Element && document.activeElement.closest('.auth-card')) {
        reset();
        return;
      }
      if (event.target instanceof Element && event.target.closest('.auth-card,.auth-motion-toggle')) {
        reset();
        return;
      }
      point = { x: event.clientX, y: event.clientY };
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const dpr = window.devicePixelRatio || 1;
        const x = Math.round(Math.max(-5, Math.min(5, (point.x / window.innerWidth - 0.5) * -10)) * dpr) / dpr;
        const y = Math.round(Math.max(-4, Math.min(4, (point.y / window.innerHeight - 0.5) * -8)) * dpr) / dpr;
        layer!.style.transform = `translate(${x}px, ${y}px)`;
      });
    }
    function focus(event: FocusEvent) {
      if (event.target instanceof Element && event.target.closest('.auth-card')) reset();
    }
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('blur', reset);
    document.documentElement.addEventListener('pointerleave', reset);
    document.addEventListener('focusin', focus);
    return () => {
      reset();
      window.removeEventListener('pointermove', move);
      window.removeEventListener('blur', reset);
      document.documentElement.removeEventListener('pointerleave', reset);
      document.removeEventListener('focusin', focus);
    };
  }, [enabled]);

  function toggleMotion() {
    const next = enabled ? 'off' : 'on';
    setPreference(next);
    try {
      localStorage.setItem(storageKey, next);
    } catch {
      /* Private browsing may deny storage. */
    }
  }

  return { imageRef, motionRef, enabled, preference, toggleMotion };
}
