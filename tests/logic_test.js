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
  'requestAnimationFrame(step);\n  globalThis.__sg = { state, cfg, popGroup, findGroup, largestGroup, blocksLeft, newGame, undo, shuffle, step };\n\n  // Test/debug hook'
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
console.log('\n' + (fails.length ? 'FAIL' : 'ALL CHECKS PASSED'));
fails.forEach((f) => console.log(' -', f));
process.exit(fails.length ? 1 : 0);
