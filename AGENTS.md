# AGENTS.md

Working notes for this repo. English. Facts about the current state, not history.

## What this is

Single-file browser game (`index.html`, no dependencies) + Python/Node test and measurement scripts.
Everything in the game lives in one IIFE; the DOM is a static shell and the board is a `<canvas>`.

## Layout

```
samegame/
├── index.html            # the game
├── AGENTS.md             # working notes for agents
├── README.md             # player-facing, keep it non-technical
├── screenshot.png        # used by README
├── LICENSE
├── pyproject.toml        # playwright (uv venv)
├── scripts/
│   ├── play.py           # automated playthrough (prints the board)
│   ├── screenshot.py     # captures a screenshot of the game
│   └── cpu_measure.py    # CPU cost of the render loop
└── tests/
    ├── browser_lib.py    # reusable helpers (Chrome over CDP)
    ├── test_game.py      # black-box browser test
    └── logic_test.js     # deterministic logic test (no browser)
```

## Setup

Uses the already-installed Chrome over CDP — no browser download.

```bash
uv venv && uv pip install playwright
```

## Commands

```bash
node tests/logic_test.js                          # deterministic logic test, DOM stubbed
uv run python tests/test_game.py                  # black-box browser test
uv run python scripts/play.py --moves 40 --delay 0.4
uv run python scripts/screenshot.py --moves 14 --out tests/screenshot.png
uv run python scripts/cpu_measure.py              # headful, 6 s windows (README screenshot: board only, pointer off canvas)
uv run python scripts/cpu_measure.py --headless
uv run python scripts/cpu_measure.py --headless
uv run python scripts/cpu_measure.py --window 4 --experiments
```

## Render loop

`step(now)` advances state and renders **only when `dirty`**. `markDirty()` is the only way a frame
gets drawn.

What must mark dirty — any mutation that is visible on the canvas:

- phase transitions (`pop → settle`, `settle → idle`); the settle transition normalizes
  `dx/dy/scale/alpha` and needs a final frame
- live particles, live popups, `popping` blocks
- `popGroup`, `collapse`, `undo`, `shuffle`, `newGame`
- `showHint` and the timeout that clears the hint
- `layout()` — changing `cv.width/height` clears the bitmap, so the next frame must redraw
- `pointermove` / `pointerleave`, only when the hovered cell changes

Idle frames do nothing: 0 canvas ops. `filter()` on `particles`/`popups` runs only when the list is
non-empty. `lastHover` caches the hovered cell so a move inside the same cell recomputes nothing;
it is invalidated by every board mutation.

Hover and hint still render every frame while active because they pulse. That is animation, not
waste. Quantizing the pulse (~12 fps) would cut hover cost to ~5% with no visible difference — not
implemented, it changes animation smoothness.

The rAF loop keeps running at 60 fps even when idle (~3–4% of a core: loop + composition). Do not
stop it when idle: `tests/logic_test.js` depends on `step` being driven by rAF to advance phases.

## Measured cost (headful, dpr 1.36, 6 s windows)

| Situation | CPU |
|---|---|
| idle, foreground | ~4% of a core |
| hover a group | ~26% |
| tab actually hidden | 1–3% |
| idle, render forced every frame (A/B, same page) | ~35% |
| idle, headless | ~3% |

Headful and headless are **not comparable** — headless rasterizes on CPU (swiftshader) and inflates
the numbers. Always state which mode a number came from.

Approaches already measured and rejected: memoizing `createLinearGradient` by arguments made it
**worse** (57% headless) — the cost is the raster of each fill, not gradient allocation. Zeroing
`shadowBlur` does nothing at idle. DPR is already capped at 2.

## Test hooks and constraints

- `window.samegame` exposes `state, cfg, popGroup, findGroup, largestGroup, blocksLeft, newGame,
  undo, shuffle, showHint, markDirty`. Prefer reading state through it over sampling pixels.
- `tests/logic_test.js` patches the exact string `requestAnimationFrame(step);\n\n  // Test/debug
  hook` to inject its harness. Changing that line or the hook comment breaks the test.
- `tests/test_game.py` counts `clearRect` (one per `render()`) and requires 0 renders in 1 s of quiet
  idle, plus at least one render after a move.
- Pixel sampling (`read_grid`) is only meaningful when the board is quiet and the pointer is off the
  canvas: a hover highlight, a live particle, or the group badge (drawn over the group centroid) can
  cover a sample point and read as a colour that matches no palette entry. Use `wait_quiet()`.
- `document.visibilityState` can report `visible` while rAF is at 0 fps (occluded tab). Tests must
  foreground the tab.

## Conventions

- Keep `index.html` a single file with no dependencies.
- Tests use the installed Chrome over CDP via the `browser-control` skill; do not add a Playwright
  browser download.
- Keep harness sleeps sparse (`wait_for_timeout`) rather than tight polling — the point of the
  render loop is low idle CPU.
