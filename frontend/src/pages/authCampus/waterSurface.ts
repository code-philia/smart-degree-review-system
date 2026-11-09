export type WaterPoint = { x: number; y: number };

export const ART_WIDTH = 1672;
export const ART_HEIGHT = 940.5;
export const POOL_FAR = 625;
export const POOL_DEPTH = 250;
const WATER_TOP_POINTS = [[110, 628], [322, 628], [325, 648], [603, 648], [607, 628], [1672, 628]];
const WATER_BOTTOM_POINTS = [[110, 672], [173, 672], [179, 731], [190, 723], [204, 715], [222, 711], [232, 704], [235, 687], [248, 680], [255, 681], [263, 691], [274, 697], [290, 691], [320, 682], [345, 677], [365, 678], [378, 672], [390, 666], [410, 656], [430, 648], [450, 643], [470, 640], [485, 640], [495, 645], [510, 650], [525, 655], [540, 662], [551, 669], [560, 673], [567, 682], [574, 697], [580, 710], [586, 728], [595, 744], [610, 764], [625, 777], [656, 779], [740, 785], [1000, 807], [1250, 827], [1470, 847], [1672, 866]];
// Actual visible water beneath the raised hand and inside its finger arch.
// These small, inset convex regions avoid treating the whole area below
// the upper silhouette as solid foreground.
const HAND_WATER_WINDOWS = [
  [[409, 742], [433, 744], [470, 752], [436, 756], [413, 754]],
  [[533, 718], [540, 721], [547, 726], [545, 727], [540, 724]],
];
function interpolateContour(points: number[][], x: number) {
  for (let i = 1; i < points.length; i++) {
    if (x <= points[i][0]) {
      const [ax, ay] = points[i - 1], [bx, by] = points[i];
      return ay + (by - ay) * Math.max(0, Math.min(1, (x - ax) / (bx - ax)));
    }
  }
  return points[points.length - 1][1];
}
function waterDistance(x: number, y: number) {
  return Math.min(
    x - 110, ART_WIDTH - x,
    y - interpolateContour(WATER_TOP_POINTS, x),
    interpolateContour(WATER_BOTTOM_POINTS, x) - y,
  );
}
function convexWaterDistance(points: number[][], x: number, y: number) {
  let distance = Infinity;
  for (let i = 0; i < points.length; i++) {
    const [ax, ay] = points[i], [bx, by] = points[(i + 1) % points.length];
    const dx = bx - ax, dy = by - ay;
    distance = Math.min(distance, (dx * (y - ay) - dy * (x - ax)) / Math.hypot(dx, dy));
  }
  return distance;
}
function featherWater(distance: number, width: number) {
  const t = Math.max(0, Math.min(1, distance / width));
  return t * t * (3 - 2 * t);
}
export function waterMaskAlpha(x: number, y: number) {
  let alpha = featherWater(waterDistance(x, y), 6);
  for (const points of HAND_WATER_WINDOWS) {
    alpha = Math.max(alpha, featherWater(convexWaterDistance(points, x, y), 2));
  }
  return alpha;
}
export const isInPool = (x: number, y: number) => waterMaskAlpha(x, y) >= 0.999;
function contourGLSL(name: string, points: number[][]) {
  return 'float ' + name + '(float x){' + points.slice(1).map(([bx, by], i) => {
    const [ax, ay] = points[i];
    return 'if(x<=' + bx + '.)return mix(' + ay + '.,' + by +
      '.,clamp((x-' + ax + '.)/' + (bx - ax) + '.,0.,1.));';
  }).join('') + 'return ' + points[points.length - 1][1] + '.;}';
}
function convexWaterGLSL(name: string, points: number[][]) {
  const fixed = (value: number) => Number(value).toFixed(8);
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  return 'float ' + name + '(vec2 p){' +
    'if(p.x<' + fixed(Math.min(...xs)) + '||p.x>' + fixed(Math.max(...xs)) +
    '||p.y<' + fixed(Math.min(...ys)) + '||p.y>' + fixed(Math.max(...ys)) +
    ')return -1000.;float d=10000.;' +
    points.map(([ax, ay], i) => {
      const [bx, by] = points[(i + 1) % points.length];
      const dx = bx - ax, dy = by - ay, length = Math.hypot(dx, dy);
      return 'd=min(d,dot(p-vec2(' + fixed(ax) + ',' + fixed(ay) +
        '),vec2(' + fixed(-dy / length) + ',' + fixed(dx / length) + ')));';
    }).join('') + 'return d;}';
}
export const POOL_GLSL = 'uniform vec2 photoPosition;' +
  contourGLSL('poolTop', WATER_TOP_POINTS) +
  contourGLSL('poolBottom', WATER_BOTTOM_POINTS) +
  HAND_WATER_WINDOWS.map((points, i) => convexWaterGLSL('handWater' + i, points)).join('') +
  'float waterMask(vec2 p){float d=min(min(p.x-110.,1672.-p.x),' +
  'min(p.y-poolTop(p.x),poolBottom(p.x)-p.y));float a=smoothstep(0.,6.,d);' +
  HAND_WATER_WINDOWS.map((_, i) => 'a=max(a,smoothstep(0.,2.,handWater' + i + '(p)));').join('') +
  'return a;}';
export function sourcePoint(clientX: number, clientY: number, rect: Pick<DOMRect, "left" | "top" | "width" | "height">, position: WaterPoint) {
  const scale = Math.max(rect.width / ART_WIDTH, rect.height / ART_HEIGHT);
  return {
    x: (clientX - rect.left - (rect.width - ART_WIDTH * scale) * position.x) / scale,
    y: (clientY - rect.top - (rect.height - ART_HEIGHT * scale) * position.y) / scale,
  };
}

export class WaterWaveSolver {
  height: Float32Array;
  next: Float32Array;
  velocity: Float32Array;
  kx: number;
  readonly ky = 0.24;
  constructor(
    public cols = 384,
    public rows = 160,
    public aspect = 4.8,
  ) {
    this.height = new Float32Array(cols * rows);
    this.next = new Float32Array(cols * rows);
    this.velocity = new Float32Array(cols * rows);
    this.kx = this.ky * (1 / (rows - 1) / (aspect / (cols - 1))) ** 2;
  }
  disturb(u: number, v: number, amplitude: number, radius = 0.03) {
    const { cols, rows, aspect } = this;
    const cx = u * (cols - 1),
      cy = v * (rows - 1),
      rx = (radius / aspect) * (cols - 1),
      ry = radius * (rows - 1);
    for (let y = Math.max(2, Math.floor(cy - ry)); y <= Math.min(rows - 3, Math.ceil(cy + ry)); y++) {
      for (let x = Math.max(2, Math.floor(cx - rx)); x <= Math.min(cols - 3, Math.ceil(cx + rx)); x++) {
        const r = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2;
        if (r >= 1) continue;
        const i = y * cols + x;
        this.height[i] = Math.max(-0.6, Math.min(0.6, this.height[i] + amplitude * (1 - r) ** 3));
      }
    }
  }
  stroke(from: WaterPoint, to: WaterPoint, strength = 0.026) {
    const dx = (to.x - from.x) * this.aspect,
      dy = to.y - from.y,
      distance = Math.hypot(dx, dy);
    const steps = Math.min(14, Math.max(1, Math.ceil(distance / 0.028))),
      length = distance || 1;
    for (let step = 1; step <= steps; step++) {
      const f = step / steps,
        u = from.x + (to.x - from.x) * f,
        v = from.y + (to.y - from.y) * f;
      this.disturb(u, v, -strength, 0.025);
      this.disturb(u + ((dx / length) * 0.022) / this.aspect, v + (dy / length) * 0.022, strength, 0.025);
    }
  }
  step() {
    const { cols, rows, height, next, velocity, kx, ky } = this;
    for (let y = 1; y < rows - 1; y++)
      for (let x = 1; x < cols - 1; x++) {
        const i = y * cols + x,
          h = height[i];
        const acceleration =
          kx * (height[i - 1] + height[i + 1] - 2 * h) + ky * (height[i - cols] + height[i + cols] - 2 * h);
        const edge = Math.min(x, cols - 1 - x, y, rows - 1 - y);
        const speed = (velocity[i] + acceleration) * (edge < 5 ? 0.9 + edge * 0.018 : 0.989);
        velocity[i] = speed;
        next[i] = Math.max(-0.65, Math.min(0.65, (h + speed) * 0.999));
      }
    this.height = next;
    this.next = height;
  }
  energy() {
    return this.height.reduce((sum, h, i) => sum + h * h + this.velocity[i] ** 2, 0);
  }
  encode(target: Uint8Array) {
    for (let i = 0; i < this.height.length; i++) {
      const code = Math.round((this.height[i] + 1) * 32767.5),
        offset = i * 4;
      target[offset] = code >>> 8;
      target[offset + 1] = code & 255;
      target[offset + 2] = 0;
      target[offset + 3] = 255;
    }
    return target;
  }
}
