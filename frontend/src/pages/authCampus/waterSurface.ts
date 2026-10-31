export const ART_WIDTH = 1672;
export const ART_HEIGHT = 941;
export type WaterPoint = { x: number; y: number };

// Conservative inner edge of the curved pool: pavement and bank plants stay still.
const bank = [
  [750, 165],
  [795, 200],
  [835, 204],
  [855, 240],
  [885, 340],
  [915, 445],
  [941, 535],
];
export function poolLeft(y: number) {
  for (let i = 1; i < bank.length; i++) {
    if (y <= bank[i][0]) {
      const [ay, ax] = bank[i - 1],
        [by, bx] = bank[i];
      return ax + (bx - ax) * Math.max(0, Math.min(1, (y - ay) / (by - ay)));
    }
  }
  return 535;
}
export const poolRight = (y: number) => 1330 + 100 * Math.max(0, Math.min(1, (y - 750) / 191));
export const isInPool = (x: number, y: number) => y >= 750 && y <= 941 && x >= poolLeft(y) && x <= poolRight(y);
export const POOL_PATH = `M165 750 H1330 L1430 941 L535 941 ${bank
  .slice(0, -1)
  .reverse()
  .map(([y, x]) => `L${x} ${y}`)
  .join(' ')} Z`;
export const POOL_GLSL = `float poolLeft(float y){${bank
  .slice(1)
  .map(([by, bx], i) => {
    const [ay, ax] = bank[i];
    return `if(y<=${by}.)return mix(${ax}.,${bx}.,clamp((y-${ay}.)/${by - ay}.,0.,1.));`;
  })
  .join('')}return 535.;}float poolRight(float y){return mix(1330.,1430.,clamp((y-750.)/191.,0.,1.));}`;

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
