import { useEffect, useRef, type CSSProperties } from 'react';
import { startPondRenderer } from './pondRenderer';
import { startBreezeRenderer } from './windRenderer';

export default function AuthCampusScene() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<HTMLDivElement>(null);
  const breeze = useRef<HTMLDivElement>(null);
  const art = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const surface = canvas.current, image = scene.current, layer = breeze.current, leaves = art.current;
    if (!surface || !image || !layer || !leaves) return;
    const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let stop: (() => void) | undefined;
    function unmount() {
      stop?.();
      stop = undefined;
      layer!.dataset.active = 'false';
    }
    function mount() {
      surface!.hidden = Boolean(motion?.matches);
      if (motion?.matches || stop) return;
      const water = startPondRenderer(surface!, image!);
      const wind = startBreezeRenderer(layer!, leaves!, image!);
      stop = () => { water(); wind(); };
    }
    function changed() { unmount(); mount(); }
    motion?.addEventListener?.('change', changed);
    window.addEventListener('pagehide', unmount);
    window.addEventListener('pageshow', mount);
    mount();
    return () => {
      unmount();
      motion?.removeEventListener?.('change', changed);
      window.removeEventListener('pagehide', unmount);
      window.removeEventListener('pageshow', mount);
    };
  }, []);
  return <>
    <link rel="preload" as="image" href="/login-campus-B-v5-b25c6008.png" fetchPriority="high" />
    <canvas ref={canvas} className="pond-water-canvas" aria-hidden="true" />
    <div ref={scene} className="scene" aria-hidden="true" />
    <div className="wash" aria-hidden="true" />
<div ref={breeze} className="preview-breeze" aria-hidden="true" data-active="true" data-ready="false">
 <div ref={art} className="breeze-art">
  <div className="breeze-canopy">
   <svg className="breeze-leaf" viewBox="-16 -16 32 32" style={{"--x": "12%", "--y": "10%", "--size": "19px", "--duration": "17s", "--delay": "-3s"} as CSSProperties}><path d="M-1 12C-7 4-8-7 5-14C7-4 6 5-1 12Z"/><path d="m0 11-2 5" fill="none" stroke="#957138" strokeWidth="1"/></svg>
   <svg className="breeze-leaf" viewBox="-16 -16 32 32" style={{"--x": "28%", "--y": "4%", "--size": "16px", "--duration": "20s", "--delay": "-12s"} as CSSProperties}><path d="M-1 12C-7 4-8-7 5-14C7-4 6 5-1 12Z"/><path d="m0 11-2 5" fill="none" stroke="#957138" strokeWidth="1"/></svg>
   <svg className="breeze-leaf" viewBox="-16 -16 32 32" style={{"--x": "47%", "--y": "16%", "--size": "22px", "--duration": "16s", "--delay": "-7s"} as CSSProperties}><path d="M-1 12C-7 4-8-7 5-14C7-4 6 5-1 12Z"/><path d="m0 11-2 5" fill="none" stroke="#957138" strokeWidth="1"/></svg>
   <svg className="breeze-leaf" viewBox="-16 -16 32 32" style={{"--x": "63%", "--y": "27%", "--size": "15px", "--duration": "18s", "--delay": "-1s"} as CSSProperties}><path d="M-1 12C-7 4-8-7 5-14C7-4 6 5-1 12Z"/><path d="m0 11-2 5" fill="none" stroke="#957138" strokeWidth="1"/></svg>
   <svg className="breeze-leaf" viewBox="-16 -16 32 32" style={{"--x": "36%", "--y": "39%", "--size": "18px", "--duration": "21s", "--delay": "-16s"} as CSSProperties}><path d="M-1 12C-7 4-8-7 5-14C7-4 6 5-1 12Z"/><path d="m0 11-2 5" fill="none" stroke="#957138" strokeWidth="1"/></svg>
  </div>
  <svg className="breeze-grass" viewBox="0 0 220 100">
   <g><path d="M10 100Q10 61 2 37M13 100Q16 54 34 31M16 100Q20 72 41 62M20 100Q31 43 57 18M23 100Q30 68 48 57M29 100Q39 72 65 69M60 100Q65 58 56 45M63 100Q74 66 88 61M65 100Q76 49 99 37"/></g>
   <g><path d="M134 100Q130 67 118 55M136 100Q139 56 157 38M141 100Q149 78 166 68M176 100Q174 66 161 56M178 100Q186 65 204 53M183 100Q197 77 219 74"/></g>
  </svg>
 </div>
</div>
  </>;
}
