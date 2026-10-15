// Motor do mascote da Sora — porte fiel de mini-video/sora-demo.html
// (makeShell, buildGrid, bodyPoint, drawBodyDots, drawEyes, floorGlow, drawMainParticles).
// Um único requestAnimationFrame compartilhado por todas as instâncias,
// um único IntersectionObserver e canvases de rascunho compartilhados.
import type { Movimento } from '../../types';

export type OrbState =
  | 'arriving'      // pontos espalhados se juntam, olhos abrem (primeira abertura)
  | 'idle'          // respira, gira devagar, pisca
  | 'listening'     // superfície ondula, olhos olham para o campo de texto (lookAt)
  | 'thinking'      // THINKING ORB: Sora pensando/processando (substitui spinners)
  | 'coordinating'  // gira devagar (avatar na barra lateral)
  | 'working'       // agente trabalhando: usa o `movimento` próprio
  | 'done';         // calma, olhos abertos

export interface OrbParams {
  size: number;
  color: string;
  state: OrbState;
  movimento: Movimento;
  lookAt: { x: number; y: number } | null;
  pulseKey: number | undefined;
  glow: boolean;
  seed: number;
  onArrived?: () => void;
}

type RGB = [number, number, number];
type V3 = [number, number, number];

// ---------- utilidades (iguais à demo) ----------
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const smooth = (t: number) => { t = clamp(t); return t * t * (3 - 2 * t); };
const eio = (t: number) => { t = clamp(t); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
const eback = (t: number) => { t = clamp(t); const c = 1.6; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };
const prog = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
const pulseAt = (t: number, at: number, w = 0.15) => Math.exp(-Math.pow((t - at) / w, 2));
const mixc = (c1: RGB, c2: RGB, t: number): RGB => [lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t)];
const rgba = (c: RGB, a: number) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
function rand(i: number) { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
const TAU = Math.PI * 2;

function hexToRgb(hex: string): RGB {
  let h = hex.trim().replace('#', '');
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  const n = parseInt(h.slice(0, 6), 16);
  if (Number.isNaN(n)) return [226, 236, 255];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// ---------- corpo: duas cascas de pontos (capuz + tigela) ----------
function norm3(x: number, y: number, z: number): V3 { const l = Math.hypot(x, y, z); return [x / l, y / l, z / l]; }
function cross3(a: V3, b: V3): V3 { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
interface Shell { A: V3; E1: V3; E2: V3; phMax: number; rad: number; bright: number }
function makeShell(axis: V3, phMax: number, rad: number, bright: number): Shell {
  const A = norm3(...axis), E1 = norm3(...cross3(A, [0, 0, 1])), E2 = cross3(A, E1);
  return { A, E1, E2, phMax, rad, bright };
}
const SHELLS = [
  makeShell([0.4, -0.6, -0.69], Math.acos(-0.5), 1.03, 1.0),   // capuz
  makeShell([-0.15, 0.8, -0.58], Math.acos(-0.25), 1.0, 0.92), // tigela
];
const HOOD_EDGE = Math.cos(SHELLS[0].phMax) + 0.02;

interface Grid {
  n: number;
  sh: Uint8Array; th: Float32Array; ph: Float32Array;
  r2: Float32Array; sx: Float32Array; sy: Float32Array; sz: Float32Array;
  q: Float32Array; // chave de densidade (drawMainParticles)
  // pré-calculados por ponto (economizam trigonometria a cada quadro)
  cth: Float32Array; sth: Float32Array; cph: Float32Array; sph: Float32Array; rim: Float32Array;
}
function buildGrid(spec: [number, number][]): Grid {
  let n = 0; for (const [m, k] of spec) n += m * k;
  const g: Grid = {
    n, sh: new Uint8Array(n), th: new Float32Array(n), ph: new Float32Array(n), q: new Float32Array(n),
    r2: new Float32Array(n), sx: new Float32Array(n), sy: new Float32Array(n), sz: new Float32Array(n),
    cth: new Float32Array(n), sth: new Float32Array(n), cph: new Float32Array(n), sph: new Float32Array(n), rim: new Float32Array(n),
  };
  let p = 0;
  spec.forEach(([m, k], sh) => {
    for (let j = 0; j < k; j++) for (let i = 0; i < m; i++) {
      g.sh[p] = sh; g.th[p] = i / m * TAU; g.ph[p] = lerp(0.3, SHELLS[sh].phMax, j / (k - 1));
      g.r2[p] = rand(p + 999); g.q[p] = rand(p + 55);
      g.cth[p] = Math.cos(g.th[p]); g.sth[p] = Math.sin(g.th[p]);
      g.cph[p] = Math.cos(g.ph[p]); g.sph[p] = Math.sin(g.ph[p]);
      g.rim[p] = Math.exp(-Math.pow((SHELLS[sh].phMax - g.ph[p]) / 0.12, 2));
      g.sx[p] = (rand(p + 77) - 0.5) * 2.7; g.sy[p] = (rand(p + 177) - 0.5) * 2.7; g.sz[p] = rand(p + 277);
      p++;
    }
  });
  return g;
}
// Grades exatamente como na demo. Duas regras de desenho, também da demo:
//  • Sora principal (cor branca, R ≥ 34): drawMainParticles — GRID_MAIN com descarte por densidade
//    (R/100)^1,5 e pontos ampliados abaixo de R 100;
//  • agentes e avatares: drawBodyDots — GRID_L (R>55) / GRID_M (R>22) / GRID_S.
let GRIDS: { main: Grid; l: Grid; m: Grid; s: Grid } | null = null;
interface DotRule { grid: Grid; density: number; dot: (s: number) => number }
function dotRule(R: number, main: boolean): DotRule {
  if (!GRIDS) GRIDS = {
    main: buildGrid([[60, 44], [60, 40]]),
    l: buildGrid([[40, 21], [40, 21]]), m: buildGrid([[28, 14], [28, 13]]), s: buildGrid([[18, 8], [18, 8]]),
  };
  if (main && R >= 34) {
    const k = 1.75 * R / 230 * (R < 100 ? lerp(2.2, 1, clamp((R - 16) / 84)) : 1);
    return { grid: GRIDS.main, density: clamp(Math.pow(R / 100, 1.5), 0.1, 1), dot: s => Math.max(0.55, k * s) };
  }
  const k = 1.6 * R / 150 * (R < 60 ? 1.45 : 1);
  return { grid: R > 55 ? GRIDS.l : R > 22 ? GRIDS.m : GRIDS.s, density: 1, dot: s => Math.max(0.55, k * s) };
}

// Parâmetros contínuos do corpo num quadro (todos suavizados — sem pulos).
interface Body {
  cx: number; cy: number; R: number; t: number; rot: number; seed: number; bph: number;
  listen: number; pulse: number; wG: number; w0: number; w1: number; w2: number;
  think: number; breath: number;
  cr: [number, number]; sr: [number, number]; // cos/sen da rotação de cada casca neste quadro
  r0: number;                                 // respiração deste quadro
}
const OUT = { x: 0, y: 0, z: 0, b: 0, a: 0, s: 0 };

// bodyPoint da demo, com os tipos de movimento misturados por peso (transição suave entre eles)
// + o estado "pensando" (faixas de luz em hélice e respiração de brilho; a forma não muda).
function bodyPoint(g: Grid, idx: number, B: Body) {
  const sh = g.sh[idx], th = g.th[idx], ph = g.ph[idx];
  const S = SHELLS[sh], t = B.t;
  let r = B.r0;
  if (B.listen > 0.001) r *= 1 + B.listen * 0.055 * Math.sin(ph * 7 - t * 9);
  const work = Math.min(1, B.wG + B.w0 + B.w1 + B.w2);
  let ct: number, st: number;
  if (B.w1 > 0.001) {                                                                // Luna: espiral
    const thv = th + B.rot * (sh ? -0.8 : 1) + B.w1 * 0.9 * Math.sin(ph * 2.2 + t * 3.2);
    ct = Math.cos(thv); st = Math.sin(thv);
  } else {
    const cr = B.cr[sh], sr = B.sr[sh], c0 = g.cth[idx], s0 = g.sth[idx];
    ct = c0 * cr - s0 * sr; st = s0 * cr + c0 * sr;
  }
  if (B.w2 > 0.001) r *= 1 + B.w2 * 0.07 * Math.sin(th * 5 + t * 6) * Math.sin(ph);       // Nina: ondas
  if (B.w0 > 0.001) r *= 1 + B.w0 * 0.03 * Math.sin(ph * 12 + t * 14);                    // Atlas: vibração
  if (B.think > 0.001) r *= 1 + B.think * 0.012 * Math.sin(t * 2.1);                      // respiração suave
  if (work > 0.001) r += work * 0.018 * Math.sin(idx * 12.9898 + t * 9);
  if (B.pulse > 0.001) r += B.pulse * (0.05 + 0.025 * Math.sin(ph * 6 - t * 18));
  const cp = g.cph[idx], sp = g.sph[idx];
  const dx = cp * S.A[0] + sp * (ct * S.E1[0] + st * S.E2[0]);
  const dy = cp * S.A[1] + sp * (ct * S.E1[1] + st * S.E2[1]);
  const dz = cp * S.A[2] + sp * (ct * S.E1[2] + st * S.E2[2]);
  const rr = r * S.rad;
  const x = dx * rr * 1.05, yy = dy * rr * 0.96, z2 = dz * rr;
  const top = clamp(0.5 - yy * 0.6 + x * 0.15 + z2 * 0.3);
  const front = smooth((dz + 0.06) / 0.22);
  let b = (0.14 + 0.95 * top) * S.bright;
  b += 0.35 * front * g.rim[idx];
  let s = lerp(0.72, 1.6, top) * lerp(0.7, 1, front);
  let a = lerp(0.05, 1, front);
  if (sh === 1 && dx * SHELLS[0].A[0] + dy * SHELLS[0].A[1] + dz * SHELLS[0].A[2] > HOOD_EDGE) a *= 0.18;
  if (B.w0 > 0.001) b += B.w0 * 0.9 * Math.exp(-Math.pow((yy - Math.sin(t * 2.6) * 0.9) / 0.09, 2)); // faixa de varredura
  if (work > 0.001) b += work * 0.5 * Math.max(0, Math.sin(idx * 7.13 + t * 11)) ** 12;               // faíscas
  if (B.think > 0.001) {
    // "pensando": a forma fica intacta; a energia é LUZ. Duas faixas em hélice (no espaço do corpo
    // inteiro, contínuas entre capuz e tigela) sobem girando + uma onda de brilho que respira de
    // cima para baixo.
    const ang = Math.atan2(z2, x);
    const u = ang / TAU * 2 - yy * 0.8 + t * 0.4;
    const band = Math.pow(0.5 + 0.5 * Math.cos(u * TAU), 4);
    const wave = 0.5 + 0.5 * Math.sin(t * 2.1 + yy * 2.2);
    // a iluminação passa a vir das faixas: o corpo apaga para ~30–45 % e as faixas acendem por cima
    const lit = b * (0.2 + 0.15 * wave) + 1.6 * band * lerp(0.35, 1, front) * (0.75 + 0.25 * wave);
    b = lerp(b, lit, B.think);
    s *= 1 + B.think * 0.3 * band;
  }
  const persp = 1 + z2 * 0.12;
  OUT.x = B.cx + x * B.R * persp; OUT.y = B.cy + yy * B.R * persp; OUT.z = z2;
  OUT.b = b; OUT.a = a; OUT.s = s;
  return OUT;
}

// ---------- canvases de rascunho compartilhados ----------
// Duas faixas de tamanho: o Chrome acelera (GPU) canvases grandes e não os pequenos; copiar de um
// rascunho acelerado para um canvas pequeno força leitura da GPU a cada quadro. Cada faixa tem o seu.
const SMALL_MAX = 192;
const layers: { c: HTMLCanvasElement; x: CanvasRenderingContext2D }[] = [];
let layer: HTMLCanvasElement | null = null;
let small: HTMLCanvasElement | null = null, sx: CanvasRenderingContext2D | null = null;
let FILTER_OK: boolean | null = null;
function scratch(w: number, h: number) {
  const tier = Math.max(w, h) <= SMALL_MAX ? 0 : 1;
  if (!layers[tier]) {
    const c = document.createElement('canvas');
    if (tier === 0) { c.width = SMALL_MAX; c.height = SMALL_MAX; }
    layers[tier] = { c, x: c.getContext('2d')! };
  }
  if (FILTER_OK === null) {
    small = document.createElement('canvas'); sx = small.getContext('2d');
    const x = layers[tier].x;
    FILTER_OK = typeof x.filter === 'string';
    if (FILTER_OK) { x.filter = 'blur(2px)'; FILTER_OK = x.filter === 'blur(2px)'; x.filter = 'none'; }
  }
  const L = layers[tier];
  if (L.c.width < w || L.c.height < h) {
    L.c.width = Math.max(L.c.width, w); L.c.height = Math.max(L.c.height, h);
  }
  layer = L.c;
  return L.x;
}

// Baldes de brilho × alfa: em vez de 1 fill por ponto, 1 fill por balde (muito mais rápido).
const NB = 12, NA = 9, NBK = NB * NA;
let bx = new Float32Array(0), by = new Float32Array(0), br = new Float32Array(0), bk = new Uint16Array(0);
const cnt = new Uint32Array(NBK + 1);
let order = new Uint32Array(0);
function ensureBuf(n: number) {
  if (bx.length >= n) return;
  bx = new Float32Array(n); by = new Float32Array(n); br = new Float32Array(n); bk = new Uint16Array(n); order = new Uint32Array(n);
}

// ---------- uma instância ----------
const K = { fast: 7, mid: 3.6, slow: 1.8 };
const approach = (v: number, target: number, k: number, dt: number) => v + (target - v) * (1 - Math.exp(-k * dt));
const ARRIVE_FORM = 1.3, ARRIVE_EYES = [1.12, 1.5] as const; // chegada ~1,6 s

export class OrbRenderer {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  p: OrbParams;
  private colKey = ''; private main = true; private col: RGB = [226, 236, 255]; private eyeCol: RGB = [236, 244, 255];
  private styles: string[] = [];
  private last = -1; private t = 0; private rot = 0; private bph = 0;
  // valores suavizados
  private v = { listen: 0, wG: 0, w0: 0, w1: 0, w2: 0, think: 0, rotSpeed: 0.28, breath: 1, breathSpeed: 1,
    eyes: 1, lookX: 0, lookY: 0, glow: 1, thinkT: 0 };
  private arriveT = Infinity;  // segundos desde o início da chegada (Infinity = já chegou)
  private arrivedFired = true;
  private pulses: { at: number; amp: number }[] = [];
  private pulseKey: number | undefined;
  private prevState: OrbState | null = null;
  private nextBlink = 0; private blinks: number[] = [];
  private dpr = 1;

  constructor(canvas: HTMLCanvasElement, p: OrbParams) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d')!;
    this.p = p;
    this.t = (p.seed * 7.31) % 50;
    this.rot = p.seed * 1.7;
    this.nextBlink = this.t + 1.5 + rand(p.seed + 3) * 3;
    this.pulseKey = p.pulseKey;
    if (p.state === 'arriving') this.startArrive();
    this.snap();
  }

  setParams(p: OrbParams) {
    if (p.pulseKey !== this.pulseKey) {
      if (p.pulseKey !== undefined) this.pulses.push({ at: this.t, amp: 0.85 });
      this.pulseKey = p.pulseKey;
    }
    if (p.state === 'arriving' && this.p.state !== 'arriving') this.startArrive();
    this.p = p;
  }

  private startArrive() { this.arriveT = 0; this.arrivedFired = false; this.v.eyes = 0; }

  private targets() {
    const { state, movimento } = this.p;
    const T = { listen: 0, wG: 0, w0: 0, w1: 0, w2: 0, think: 0, rotSpeed: 0.28, breath: 1, breathSpeed: 1,
      eyes: 1, lookX: 0, lookY: 0 };
    const look = this.p.lookAt;
    if (look) { T.lookX = clamp(look.x, -1, 1); T.lookY = clamp(look.y, -1, 1); }
    switch (state) {
      case 'listening':
        T.listen = 0.7; T.rotSpeed = 0.34;
        if (!look) T.lookY = 0.9;
        break;
      case 'thinking':
        T.think = 1; T.rotSpeed = 0.5; T.eyes = 0.7; T.breath = 0.6;
        T.lookY = -0.85; T.lookX = 0.35 * Math.sin(this.t * 0.7);
        break;
      case 'coordinating':
        T.rotSpeed = 0.4;
        break;
      case 'working': {
        const w = 0.85;
        if (movimento === 'vibracao') { T.w0 = w; T.rotSpeed = 0.45; }
        else if (movimento === 'espiral') { T.w1 = w; T.rotSpeed = 0.45; }
        else if (movimento === 'ondas') { T.w2 = w; T.rotSpeed = 0.45; }
        else { T.wG = 0.55; T.rotSpeed = 1.15; }
        break;
      }
      case 'done':
        T.rotSpeed = 0.18; T.breath = 0.8; T.breathSpeed = 0.7;
        break;
      default: break; // idle / arriving
    }
    return T;
  }

  /** Aplica os alvos imediatamente (redução de movimento / primeiro quadro). */
  snap() {
    const T = this.targets();
    Object.assign(this.v, T);
    this.v.glow = this.p.glow ? 1 : 0;
    this.v.thinkT = 0;
    if (this.arriveT !== Infinity && this.arriveT < ARRIVE_EYES[1]) this.v.eyes = 0;
  }

  private ensureColor() {
    if (this.colKey === this.p.color) return;
    this.colKey = this.p.color;
    this.col = hexToRgb(this.p.color);
    this.main = this.col[0] === 226 && this.col[1] === 236 && this.col[2] === 255; // a Sora (não um agente)
    this.eyeCol = mixc(this.col, [236, 244, 255], 0.6);
    this.styles = [];
    for (let i = 0; i < NB; i++) {
      const bb = (i + 0.5) / NB * 1.6;
      for (let j = 0; j < NA; j++) {
        const a = ((j + 1) / NA) ** 2; // níveis quadráticos: alfas baixos ficam precisos
        this.styles.push(`rgba(${Math.min(255, this.col[0] * bb) | 0},${Math.min(255, this.col[1] * bb) | 0},${Math.min(255, this.col[2] * bb) | 0},${a.toFixed(3)})`);
      }
    }
  }

  /** Quadro determinístico (QA / comparação com a demo): tempo e rotação fixos, estado já assentado. */
  renderAt(t: number, rot: number) {
    this.arriveT = Infinity; this.pulses.length = 0; this.blinks = [];
    this.t = t; this.snap();
    this.rot = rot; this.bph = t * 1.8; this.v.thinkT = t;
    this.draw();
  }

  /** Um quadro. `now` em ms; `still` = quadro estático (prefers-reduced-motion). */
  frame(now: number, still = false) {
    const dt = still ? 0 : this.last < 0 ? 1 / 60 : clamp((now - this.last) / 1000, 0, 0.05);
    this.last = now;
    const p = this.p, v = this.v;
    if (p.state !== this.prevState) {
      if (p.state === 'done' && this.prevState !== null) this.pulses.push({ at: this.t, amp: 0.6 });
      this.prevState = p.state;
    }
    if (still) {
      this.arriveT = Infinity;
      this.pulses.length = 0;
      this.snap();
      this.t = 1.3 + p.seed * 0.37;
      this.rot = 0.6 + p.seed;
      this.bph = this.t * 1.8;
      if (!this.arrivedFired) { this.arrivedFired = true; p.onArrived?.(); }
    } else {
      this.t += dt;
      const T = this.targets();
      v.listen = approach(v.listen, T.listen, K.mid, dt);
      v.wG = approach(v.wG, T.wG, K.slow, dt);
      v.w0 = approach(v.w0, T.w0, K.slow, dt);
      v.w1 = approach(v.w1, T.w1, K.slow, dt);
      v.w2 = approach(v.w2, T.w2, K.slow, dt);
      v.think = approach(v.think, T.think, K.slow, dt);
      v.rotSpeed = approach(v.rotSpeed, T.rotSpeed, K.slow, dt);
      v.breath = approach(v.breath, T.breath, K.slow, dt);
      v.breathSpeed = approach(v.breathSpeed, T.breathSpeed, K.slow, dt);
      if (this.arriveT === Infinity) v.eyes = approach(v.eyes, T.eyes, K.mid, dt);
      v.lookX = approach(v.lookX, T.lookX, K.mid, dt);
      v.lookY = approach(v.lookY, T.lookY, K.mid, dt);
      v.glow = approach(v.glow, p.glow ? 1 : 0, K.mid, dt);
      v.thinkT += dt * v.think;
      this.rot += v.rotSpeed * dt;
      this.bph += 1.8 * v.breathSpeed * dt; // respiração mais lenta no "done"
      if (this.arriveT !== Infinity) {
        this.arriveT += dt;
        if (this.arriveT >= ARRIVE_EYES[1] + 0.1) {
          this.arriveT = Infinity; v.eyes = 1;
          if (!this.arrivedFired) { this.arrivedFired = true; p.onArrived?.(); }
        }
      }
      // piscar ocasional (no "pensando" quase não pisca)
      if (this.t >= this.nextBlink) {
        this.blinks.push(this.t + 0.12);
        if (rand(this.t * 13 + p.seed) < 0.22) this.blinks.push(this.t + 0.42);
        this.nextBlink = this.t + (v.think > 0.5 ? 6 : 2.6) + rand(this.t * 7 + p.seed) * 3.6;
      }
      while (this.blinks.length && this.blinks[0] < this.t - 0.3) this.blinks.shift();
      while (this.pulses.length && this.pulses[0].at < this.t - 1.2) this.pulses.shift();
    }
    this.draw();
  }

  private draw() {
    const p = this.p, v = this.v, t = this.t;
    this.ensureColor();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.max(1, Math.round(p.size * dpr));
    if (this.canvas.width !== W || this.canvas.height !== W || this.dpr !== dpr) {
      this.canvas.width = W; this.canvas.height = W; this.dpr = dpr;
    }
    const size = p.size;
    const g = v.glow;
    const R = size * lerp(0.38, 0.345, g);
    const cx = size * 0.5, cy = size * lerp(0.5, 0.455, g);
    let pulse = 0;
    for (const q of this.pulses) pulse = Math.max(pulse, pulseAt(t, q.at + 0.18, 0.16) * q.amp);
    const B: Body = {
      cx, cy, R, t, rot: this.rot, seed: p.seed, bph: this.bph, listen: v.listen, pulse,
      wG: v.wG, w0: v.w0, w1: v.w1, w2: v.w2, think: v.think, breath: v.breath,
      cr: [Math.cos(this.rot), Math.cos(-0.8 * this.rot)], sr: [Math.sin(this.rot), Math.sin(-0.8 * this.rot)],
      r0: 1 + 0.014 * v.breath * Math.sin(this.bph + p.seed),
    };

    const rule = dotRule(R, this.main), grid = rule.grid, density = rule.density;
    const L = scratch(W, W);
    L.setTransform(1, 0, 0, 1, 0, 0);
    L.globalCompositeOperation = 'source-over';
    L.clearRect(0, 0, W, W);
    L.setTransform(dpr, 0, 0, dpr, 0, 0);
    L.globalCompositeOperation = 'lighter';

    // chegada
    const arriving = this.arriveT !== Infinity;
    const formIn = arriving ? prog(this.arriveT, 0, ARRIVE_FORM) : 1;
    const globalA = arriving ? smooth(prog(this.arriveT, 0, 0.8)) : 1;

    // pontos do corpo → baldes
    ensureBuf(grid.n);
    cnt.fill(0);
    let m = 0;
    // abaixo de R 12 (orb de ~30 px) os pontos ficam mais claros para continuar legível
    const pulseB = (1 + pulse * 0.35) * lerp(1.35, 1, clamp((R - 6) / 6));
    // abaixo de R 60 os pontos de trás (alfa ~0,05) somem sob o brilho: descartar economiza ~40%
    const minA = R > 60 ? 0.01 : 0.06;
    for (let i = 0; i < grid.n; i++) {
      let dA = 1;
      if (density < 1) {
        dA = smooth((density - grid.q[i]) / 0.05 + 0.5);
        if (dA <= 0.01) continue;
      }
      const q = bodyPoint(grid, i, B);
      let x = q.x, y = q.y, b = q.b * pulseB, a = q.a * dA, s = rule.dot(q.s);
      if (formIn < 1) {
        const fp = eio(formIn * 1.6 - grid.r2[i] * 0.6);
        if (fp < 1) {
          const sz = grid.sz[i];
          x = lerp(cx + grid.sx[i] * R, x, fp); y = lerp(cy + grid.sy[i] * R, y, fp);
          a *= lerp(0.25 + sz * 0.6, 1, fp); b = lerp(0.5 + sz * 0.5, b, fp); s *= lerp(0.6 + sz, 1, fp);
        }
      }
      a *= globalA;
      if (a < minA) continue;
      const bi = Math.min(NB - 1, (clamp(b, 0, 1.6) / 1.6 * NB) | 0);
      const ai = Math.min(NA - 1, Math.max(0, Math.round(Math.sqrt(clamp(a)) * NA) - 1));
      const key = bi * NA + ai;
      bx[m] = x; by[m] = y; br[m] = Math.max(0.55, s); bk[m] = key;
      cnt[key + 1]++;
      m++;
    }
    for (let k = 0; k < NBK; k++) cnt[k + 1] += cnt[k];
    const start = cnt.slice(0, NBK);
    for (let i = 0; i < m; i++) order[start[bk[i]]++] = i;
    let i0 = 0;
    for (let k = 0; k < NBK; k++) {
      const i1 = cnt[k + 1];
      if (i1 > i0) {
        L.fillStyle = this.styles[k];
        L.beginPath();
        for (let j = i0; j < i1; j++) {
          const o = order[j], rr = br[o];
          L.moveTo(bx[o] + rr, by[o]);
          L.arc(bx[o], by[o], rr, 0, TAU);
        }
        L.fill();
      }
      i0 = i1;
    }


    // ---- composição no canvas visível ----
    const c = this.ctx;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = 'source-over';
    c.globalAlpha = 1;
    c.clearRect(0, 0, W, W);
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (g > 0.01) this.floorGlow(cx, cy, R, (globalA * 0.9 + pulse * 0.4 + v.think * 0.25) * g);
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalCompositeOperation = 'lighter';
    this.bloom(W, R * dpr);
    c.globalAlpha = 1;
    c.drawImage(layer!, 0, 0, W, W, 0, 0, W, W);
    c.globalCompositeOperation = 'source-over';

    // "pensando": brilho interno que respira dentro da abertura, atrás dos olhos
    if (v.think > 0.01) {
      const br = 0.5 + 0.5 * Math.sin(t * 2.1);
      const ex = (cx - 0.25 * R) * dpr, ey = (cy + 0.02 * R) * dpr, rr = R * dpr * lerp(0.42, 0.55, br);
      const gr = c.createRadialGradient(ex, ey, 0, ex, ey, rr);
      gr.addColorStop(0, rgba(this.col, 0.3 * v.think * (0.55 + 0.45 * br)));
      gr.addColorStop(1, rgba(this.col, 0));
      c.globalCompositeOperation = 'lighter';
      c.fillStyle = gr; c.beginPath(); c.arc(ex, ey, rr, 0, TAU); c.fill();
      c.globalCompositeOperation = 'source-over';
    }

    // olhos
    let eyes = v.eyes;
    if (arriving) eyes = eback(prog(this.arriveT, ARRIVE_EYES[0], ARRIVE_EYES[1]));
    this.drawEyes(cx * dpr, cy * dpr, R * dpr, eyes, globalA);
  }

  private bloom(W: number, Rd: number) {
    const c = this.ctx;
    if (FILTER_OK) {
      // raios da demo (14 px e 4 px), limitados nos orbs pequenos
      const d = this.dpr, Rc = Rd / d;
      const b1 = Math.min(14, Rc * 0.9) * d, b2 = Math.min(4, Rc * 0.27) * d;
      c.filter = `blur(${b1.toFixed(1)}px)`; c.globalAlpha = 0.5; c.drawImage(layer!, 0, 0, W, W, 0, 0, W, W);
      c.filter = `blur(${b2.toFixed(1)}px)`; c.globalAlpha = 0.55; c.drawImage(layer!, 0, 0, W, W, 0, 0, W, W);
      c.filter = 'none';
    } else {
      // sem ctx.filter (Safari antigo): reduz e amplia para um desfoque barato
      const s = Math.max(4, Math.round(W / 8));
      if (small!.width !== s) { small!.width = s; small!.height = s; }
      sx!.clearRect(0, 0, s, s);
      sx!.imageSmoothingEnabled = true;
      sx!.drawImage(layer!, 0, 0, W, W, 0, 0, s, s);
      c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high';
      c.globalAlpha = 0.85; c.drawImage(small!, 0, 0, s, s, 0, 0, W, W);
    }
  }

  private floorGlow(cx: number, cy: number, R: number, alpha: number) {
    if (alpha <= 0) return;
    const c = this.ctx;
    c.save(); c.translate(cx, cy + R * 1.18); c.scale(1, 0.13);
    const gr = c.createRadialGradient(0, 0, 0, 0, 0, R * 1.1);
    gr.addColorStop(0, rgba(this.col, 0.35 * clamp(alpha, 0, 1.4)));
    gr.addColorStop(1, rgba(this.col, 0));
    c.fillStyle = gr; c.beginPath(); c.arc(0, 0, R * 1.1, 0, TAU); c.fill(); c.restore();
  }

  private drawEyes(cx: number, cy: number, R: number, open: number, vis: number) {
    if (vis <= 0.01) return;
    let blink = 1;
    for (const bt of this.blinks) { const q = Math.abs(this.t - bt); if (q < 0.12) blink = Math.min(blink, q / 0.12); }
    const v = this.v, c = this.ctx;
    const eyeK = lerp(1.4, 1, clamp((R / this.dpr - 6) / 8)); // olhos um pouco maiores abaixo de ~35 px
    const w = 0.05 * R * eyeK, h = 0.125 * R * eyeK * clamp(open, 0, 1.3) * Math.max(0.08, blink);
    const ox = -0.25 * R + v.lookX * R * 0.09, oy = 0.02 * R + v.lookY * R * 0.06;
    c.save();
    c.globalAlpha = clamp(vis);
    c.shadowColor = rgba(this.col, 0.75); c.shadowBlur = Math.max(2, R * 0.16);
    c.fillStyle = rgba(this.eyeCol, 1);
    for (const s of [-1, 1]) {
      c.beginPath();
      c.ellipse(cx + s * 0.125 * R + ox, cy + oy, Math.max(0.6, w), Math.max(0.4, h), 0, 0, TAU);
      c.fill();
    }
    c.restore();
  }
}

// ---------- agendador compartilhado ----------
const active = new Set<OrbRenderer>();
const all = new Map<Element, OrbRenderer>();
let raf = 0;
let io: IntersectionObserver | null = null;
const visible = new WeakSet<OrbRenderer>();
const mq = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
export const reducedMotion = () => !!mq?.matches;

let tick = 0;
function loop(now: number) {
  raf = 0;
  tick++;
  // avatares pequenos (≤ 40 px) desenham a 30 fps, alternados pelo seed — o movimento é
  // imperceptível nesse tamanho e a carga com muitos orbs cai pela metade
  for (const r of active) if (r.p.size > 40 || ((tick + r.p.seed) & 1) === 0) r.frame(now);
  if (active.size) raf = requestAnimationFrame(loop);
}
function wake() { if (!raf && active.size) raf = requestAnimationFrame(loop); }

function refresh(r: OrbRenderer) {
  if (visible.has(r) && !reducedMotion()) { active.add(r); wake(); }
  else {
    active.delete(r);
    if (visible.has(r)) r.frame(performance.now(), true);
  }
}
mq?.addEventListener?.('change', () => { for (const r of all.values()) refresh(r); });

function observer() {
  if (io || typeof IntersectionObserver === 'undefined') return io;
  io = new IntersectionObserver(entries => {
    for (const e of entries) {
      const r = all.get(e.target);
      if (!r) continue;
      if (e.isIntersecting) visible.add(r); else visible.delete(r);
      refresh(r);
    }
  }, { rootMargin: '64px' });
  return io;
}

export function mountOrb(r: OrbRenderer) {
  all.set(r.canvas, r);
  const o = observer();
  if (o) o.observe(r.canvas); else visible.add(r);
  r.frame(performance.now(), reducedMotion()); // primeiro quadro imediato (sem piscar vazio)
  refresh(r);
}
export function unmountOrb(r: OrbRenderer) {
  all.delete(r.canvas);
  io?.unobserve(r.canvas);
  active.delete(r);
  visible.delete(r);
}
/** Redesenha um orb parado (redução de movimento) após mudança de props. */
export function touchOrb(r: OrbRenderer) {
  if (!active.has(r) && visible.has(r)) r.frame(performance.now(), true);
}
