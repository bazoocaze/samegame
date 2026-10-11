#!/usr/bin/env node
/* Deterministic logic test — no browser, no rendering.
 * Loads the game script from index.html, stubs the DOM, plays a full game and
 * checks the rules. Run: node tests/logic_test.js
 */
const fs = require('fs');
const path = require('path');

const noop = () => {};
const grad = { addColorStop: noop };
const ctxStub = new Proxy(
  { createLinearGradient: () => grad, measureText: () => ({ width: 10 }) },
  { get: (t, k) => (k in t ? t[k] : noop), set: (t, k, v) => ((t[k] = v), true) }
);

const listeners = {};
function elNode(id) {
  return {
    id, textContent: '', innerHTML: '', disabled: false, value: '', style: {}, offsetWidth: 1,
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    appendChild: noop, onclick: null, onchange: null,
    getContext: () => ctxStub,
    getBoundingClientRect: () => ({ left: 0, top: 0 }),
    addEventListener: (type, fn) => { listeners[type] = fn; },
  };
}
const els = {};
for (const id of ['board','score','best','moves','left','hintline','overlay','ovTitle','ovText','ovBtn',
                  'undo','logo','btnNew','btnHint','btnShuffle','btnSound','btnUndo','selSize','selColors']) {
  els[id] = elNode(id);
}

global.document = {
  getElementById: (id) => els[id],
  querySelector: () => ({ clientWidth: 640, clientHeight: 400 }),
  createElement: () => ({ style: {} }),
};
global.window = { addEventListener: noop, devicePixelRatio: 1 };
global.localStorage = {
  _d: {},
  getItem: (k) => global.localStorage._d[k] ?? null,
  setItem: (k, v) => { global.localStorage._d[k] = v; },
};

let T = 0;
global.performance = { now: () => T };
let rafQueue = [];
global.requestAnimationFrame = (fn) => rafQueue.push(fn);
global.setTimeout = (fn) => { fn(); return 0; };
global.clearTimeout = noop;

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
let src = html.match(/<script>([\s\S]*?)<\/script>/)[1];
src = src.replace(
  'requestAnimationFrame(step);\n\n  // Test/debug hook',
  'requestAnimationFrame(step);\n  globalThis.__sg = { state, cfg, popGroup, findGroup, largestGroup, blocksLeft, newGame, undo, shuffle, step, PALETTE };\n\n  // Test/debug hook'
);
eval(src);

const G = globalThis.__sg;
const frames = (n) => {
  for (let i = 0; i < n; i++) {
    T += 16;
    const q = rafQueue; rafQueue = [];
    for (const f of q) f(T);
  }
};

function invariants(tag) {
  const { grid } = G.state, { cols, rows } = G.cfg;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (grid[r][c] && r + 1 < rows && !grid[r + 1][c]) {
        throw new Error(`${tag}: floating block at (${r},${c})`);
      }
    }
  }
  let emptySeen = false;
  for (let c = 0; c < cols; c++) {
    const any = Array.from({ length: rows }, (_, r) => grid[r][c]).some(Boolean);
    if (!any) emptySeen = true;
    else if (emptySeen) throw new Error(`${tag}: empty column ${c} before a filled one`);
  }
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const b = grid[r][c];
      if (b && (b.r !== r || b.c !== c)) throw new Error(`${tag}: cell index mismatch at (${r},${c})`);
    }
  }
}

const fails = [];
const total0 = G.blocksLeft();
let expected = 0, popped = 0, guard = 0, scoreBeforeLast = 0, lastGroup = 0;

while (guard++ < 500) {
  frames(30);
  invariants('settle');
  const g = G.largestGroup();
  if (g.length < 2) break;
  scoreBeforeLast = expected;
  lastGroup = g.length;
  expected += lastGroup * (lastGroup - 1);
  popped += lastGroup;
  G.popGroup(g);
  frames(30);
  invariants('after pop');
  if (G.state.score !== expected) fails.push(`score ${G.state.score} != ${expected}`);
  if (G.blocksLeft() !== total0 - popped) fails.push(`blocks ${G.blocksLeft()} != ${total0 - popped}`);
}
frames(30);
const bonus = G.blocksLeft() === 0 ? 2000 : 0;
if (G.state.score !== expected + bonus) fails.push(`final score ${G.state.score} != ${expected + bonus}`);
if (!G.state.over) fails.push('game over not detected');
console.log(`game: score=${G.state.score} moves=${G.state.moves} left=${G.blocksLeft()} over=${G.state.over}`);

// undo restores the previous snapshot
G.undo();
frames(30);
invariants('undo');
if (G.state.score !== scoreBeforeLast) fails.push(`undo score ${G.state.score} != ${scoreBeforeLast}`);
if (G.blocksLeft() !== total0 - popped + lastGroup) fails.push(`undo blocks ${G.blocksLeft()} != ${total0 - popped + lastGroup}`);
console.log(`undo: score=${G.state.score} blocks=${G.blocksLeft()}`);

// shuffle keeps the colour multiset
const before = [];
for (let r = 0; r < G.cfg.rows; r++) for (let c = 0; c < G.cfg.cols; c++) {
  const b = G.state.grid[r][c]; if (b) before.push(b.color);
}
G.shuffle();
frames(30);
invariants('shuffle');
const after = [];
for (let r = 0; r < G.cfg.rows; r++) for (let c = 0; c < G.cfg.cols; c++) {
  const b = G.state.grid[r][c]; if (b) after.push(b.color);
}
if (before.sort().join() !== after.sort().join()) fails.push('shuffle changed the multiset');
console.log('shuffle: multiset preserved');

console.log(`best persisted: ${G.state.best}`);

// palette separation — colours must stay distinguishable at cell size (CIE Lab, ΔE2000)
const MIN_SEPARATION = 26;
const lab = (c) => {
  const [r, g, b] = [c.r, c.g, c.b];
  const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const [R, G2, B] = [r, g, b].map(f);
  const X = (0.4124 * R + 0.3576 * G2 + 0.1805 * B) / 0.95047;
  const Y = 0.2126 * R + 0.7152 * G2 + 0.0722 * B;
  const Z = (0.0193 * R + 0.1192 * G2 + 0.9503 * B) / 1.08883;
  const t = (v) => v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116;
  return [116 * t(Y) - 16, 500 * (t(X) - t(Y)), 200 * (t(Y) - t(Z))];
};
const deg = (x) => ((x * 180 / Math.PI) % 360 + 360) % 360;
const de00 = (p, q) => {
  const [L1, a1, b1] = p, [L2, a2, b2] = q;
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(b2, b2), Cb = (C1 + C2) / 2;
  const Gc = 0.5 * (1 - Math.sqrt(Math.pow(Cb, 7) / (Math.pow(Cb, 7) + Math.pow(25, 7))));
  const A1 = a1 * (1 + Gc), A2 = a2 * (1 + Gc);
  const C1p = Math.hypot(A1, b1), C2p = Math.hypot(A2, b2);
  const h1 = deg(Math.atan2(b1, A1)), h2 = deg(Math.atan2(b2, A2));
  const dL = L2 - L1, dC = C2p - C1p;
  let dh = h2 - h1; if (dh > 180) dh -= 360; if (dh < -180) dh += 360;
  const dH = 2 * Math.sqrt(C1p * C2p) * Math.sin(dh * Math.PI / 360);
  const Lb = (L1 + L2) / 2, Cbp = (C1p + C2p) / 2;
  let hb = (h1 + h2) / 2;
  if (Math.abs(h1 - h2) > 180) hb = (h1 + h2 + (h1 + h2 < 360 ? 360 : -360)) / 2;
  const T = 1 - 0.17 * Math.cos((hb - 30) * Math.PI / 180) + 0.24 * Math.cos(2 * hb * Math.PI / 180)
          + 0.32 * Math.cos((3 * hb - 6) * Math.PI / 180) + 0.20 * Math.cos((4 * hb - 63) * Math.PI / 180);
  const Sl = 1 + 0.0084 * (Lb - 50), Sc = 1 + 0.045 * Cbp, Sh = 1 + 0.015 * Cbp * T;
  const Rc = 2 * Math.sqrt(Math.pow(Cbp, 7) / (Math.pow(Cbp, 7) + Math.pow(25, 7)));
  const dth = hb - 30;
  return Math.sqrt((dL / Sl) ** 2 + (dC / Sc) ** 2 + (dH / Sh) ** 2 + Rc * Math.sin(dth * Math.PI / 180) * Math.pow(dth / 30, 2));
};
const labs = G.PALETTE.map((p) => lab(p.rgb));
let worst = Infinity, worstPair = null;
for (let i = 0; i < labs.length; i++)
  for (let j = i + 1; j < labs.length; j++) {
    const d = de00(labs[i], labs[j]);
    if (d < worst) { worst = d; worstPair = `${G.PALETTE[i].name}/${G.PALETTE[j].name}`; }
  }
if (worst < MIN_SEPARATION) fails.push(`palette too close: ${worstPair} ΔE2000 ${worst.toFixed(1)} < ${MIN_SEPARATION}`);
console.log(`palette: closest pair ${worstPair} ΔE2000 ${worst.toFixed(1)} (min ${MIN_SEPARATION})`);

console.log('\n' + (fails.length ? 'FAIL' : 'ALL CHECKS PASSED'));
fails.forEach((f) => console.log(' -', f));
process.exit(fails.length ? 1 : 0);
