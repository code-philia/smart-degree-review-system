import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { startPondRenderer } from './pondRenderer';
import { POOL_PATH } from './waterSurface';

const leaves = [
  ['12%', '10%', '19px', '17s', '-3s'],
  ['28%', '4%', '16px', '20s', '-12s'],
  ['47%', '16%', '22px', '16s', '-7s'],
  ['63%', '27%', '15px', '18s', '-1s'],
  ['36%', '39%', '18px', '21s', '-16s'],
];
const gearPath = (() => {
  const points: string[] = [];
  for (let tooth = 0; tooth < 48; tooth++)
    for (const [offset, radius] of [
      [-0.06545, 82],
      [-0.03142, 87],
      [0.03142, 87],
      [0.06545, 82],
    ]) {
      const angle = (tooth * Math.PI) / 24 + offset;
      points.push(`${(Math.cos(angle) * radius).toFixed(5)},${(Math.sin(angle) * radius).toFixed(5)}`);
    }
  return `M${points.join(' L')} Z M75,0 A75,75 0 1 0 -75,0 A75,75 0 1 0 75,0 Z`;
})();

export default function AuthCampusScene() {
  const clipId = useId();
  const canvas = useRef<HTMLCanvasElement>(null),
    hit = useRef<SVGPathElement>(null),
    stage = useRef<SVGSVGElement>(null);
  const rotor = useRef<SVGGElement>(null),
    gearFrame = useRef(0),
    scene = useRef<HTMLDivElement>(null);
  const [spinning, setSpinning] = useState(false);
  const gearStart = useRef(0),
    gearPausedAt = useRef(0),
    gearDraw = useRef<FrameRequestCallback | null>(null);
  useEffect(() => {
    const stop =
      canvas.current && hit.current && stage.current
        ? startPondRenderer(canvas.current, hit.current, stage.current)
        : undefined;
    const visibility = () => {
      if (scene.current) scene.current.dataset.active = String(!document.hidden);
      if (document.hidden && gearDraw.current) {
        cancelAnimationFrame(gearFrame.current);
        gearFrame.current = 0;
        gearPausedAt.current = performance.now();
      } else if (!document.hidden && gearDraw.current && gearPausedAt.current) {
        gearStart.current += performance.now() - gearPausedAt.current;
        gearPausedAt.current = 0;
        gearFrame.current = requestAnimationFrame(gearDraw.current);
      }
    };
    visibility();
    document.addEventListener('visibilitychange', visibility);
    return () => {
      stop?.();
      cancelAnimationFrame(gearFrame.current);
      gearDraw.current = null;
      document.removeEventListener('visibilitychange', visibility);
    };
  }, []);
  function spinGear() {
    if (gearDraw.current) return;
    setSpinning(true);
    gearStart.current = performance.now();
    gearPausedAt.current = 0;
    function draw(now: number) {
      const progress = Math.min(1, (now - gearStart.current) / 6000),
        u = (progress - 2 / 3) * 3;
      const angle = progress <= 2 / 3 ? 864 * progress : 576 + 288 * u - 144 * u * u;
      rotor.current?.setAttribute('transform', `rotate(${angle.toFixed(5)} 0 0)`);
      if (progress < 1) gearFrame.current = requestAnimationFrame(draw);
      else {
        gearFrame.current = 0;
        gearDraw.current = null;
        rotor.current?.setAttribute('transform', 'rotate(0 0 0)');
        setSpinning(false);
      }
    }
    gearDraw.current = draw;
    gearFrame.current = requestAnimationFrame(draw);
  }
  return (
    <div className="campus-scene" ref={scene} data-active="true">
      <div className="campus-background" aria-hidden="true">
        <img src="/sjtu-siyuan-illustration.webp" alt="" width="1672" height="941" fetchPriority="high" />
      </div>
      <div className="campus-water" aria-hidden="true">
        <canvas ref={canvas} className="campus-water-canvas" />
        <svg ref={stage} className="campus-water-stage" viewBox="0 0 1672 941" preserveAspectRatio="xMinYMid slice">
          <path ref={hit} d={POOL_PATH} fill="transparent" stroke="none" className="campus-water-hit" />
        </svg>
      </div>
      <div className="campus-wind" aria-hidden="true">
        {leaves.map(([x, y, size, duration, delay], index) => (
          <svg
            key={index}
            className="campus-wind-leaf"
            viewBox="-16 -16 32 32"
            style={{ '--x': x, '--y': y, '--size': size, '--duration': duration, '--delay': delay } as CSSProperties}
          >
            <path d="M-1 12C-7 4-8-7 5-14C7-4 6 5-1 12Z" />
            <path d="m0 11-2 5" fill="none" stroke="#957138" strokeWidth="1" />
          </svg>
        ))}
        <svg className="campus-grass" viewBox="0 0 220 100">
          <g>
            <path d="M10 100Q10 61 2 37M13 100Q16 54 34 31M16 100Q20 72 41 62M20 100Q31 43 57 18M23 100Q30 68 48 57M29 100Q39 72 65 69M60 100Q65 58 56 45M63 100Q74 66 88 61M65 100Q76 49 99 37" />
          </g>
          <g>
            <path d="M134 100Q130 67 118 55M136 100Q139 56 157 38M141 100Q149 78 166 68M176 100Q174 66 161 56M178 100Q186 65 204 53M183 100Q197 77 219 74" />
          </g>
        </svg>
      </div>
      <svg
        className="campus-gear-stage"
        viewBox="0 0 1672 941"
        preserveAspectRatio="xMinYMid slice"
        aria-label="思源碑齿轮互动"
      >
        <defs>
          <clipPath id={clipId}>
            <rect x="560" y="178" width="220" height="161" />
          </clipPath>
        </defs>
        <g
          role="button"
          tabIndex={0}
          aria-label={spinning ? '齿轮正在旋转' : '点击齿轮，旋转两圈'}
          aria-disabled={spinning}
          className="campus-gear-button"
          onClick={spinGear}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              spinGear();
            }
          }}
        >
          <title>点击齿轮，转动两圈后缓缓停下</title>
          <circle cx="667" cy="288" r="100" fill="transparent" stroke="none" />
          <circle className="campus-gear-focus" cx="667" cy="288" r="96" />
          <g clipPath={`url(#${clipId})`}>
            <g transform="translate(667 288)">
              <g ref={rotor} className="campus-gear-rotor">
                <path d={gearPath} fill="#41372b" fillRule="evenodd" stroke="#29241d" strokeWidth=".7" />
                <circle cx="0" cy="0" r="76.5" fill="none" stroke="#917452" strokeWidth=".65" opacity=".7" />
                <path
                  d="M-32.54,-73.08 A80,80 0 0 1 -5.58,-79.8"
                  fill="none"
                  stroke="#bb955e"
                  strokeWidth="3.1"
                  strokeLinecap="round"
                />
                <path d="M-2,-85 H2" stroke="#d4b277" strokeWidth="2.5" />
              </g>
            </g>
          </g>
        </g>
      </svg>
    </div>
  );
}
