# SameGame

SameGame (Clickomania) clone in **a single HTML file**, no dependencies.
MIT licensed — [live demo](https://bazoocaze.github.io/samegame/).

```
samegame/
├── index.html            # the game
├── AGENTS.md             # working notes for agents
├── pyproject.toml        # playwright (uv venv)
├── scripts/
│   ├── play.py           # automated playthrough (prints the board)
│   ├── screenshot.py     # captures a screenshot of the game
│   └── cpu_measure.py    # CPU cost of the render loop
└── tests/
    ├── browser_lib.py    # reusable helpers (Chrome over CDP)
    ├── test_game.py      # black-box browser test
    ├── logic_test.js     # deterministic logic test (no browser)
    └── screenshot.png
```

## Rules

- Click a group of **2+ same-colour blocks** (orthogonal adjacency) to remove it.
- Blocks fall down; empty columns slide left.
- Score for a group of `n`: `n × (n − 1)`. Clearing the board: `+2000`.
- Best score per size/colour count is kept in `localStorage`.

Features: undo, hint (best group), shuffle, sound (WebAudio), hover with a points badge,
pop/fall animations, keyboard `N U H S M`.

The render loop is **render-on-change**: `render()` runs only when something actually changed
(a click, a hover change, a live pop/settle/particle/popup, a resize). An idle board draws nothing.

## Run

Open `index.html` in a browser.

## Tests

Uses the already-installed Chrome over CDP — no browser download.

```bash
uv venv && uv pip install playwright

node tests/logic_test.js          # gravity/column invariants, score, undo, shuffle
uv run python tests/test_game.py  # plays the game in the browser, checks HUD + render + persistence
uv run python scripts/play.py --moves 40 --delay 0.4
uv run python scripts/screenshot.py --moves 14 --out tests/screenshot.png
uv run python scripts/cpu_measure.py --window 4 --experiments
```

Harness notes:

- `tests/browser_lib.py` exposes `open_game`, `read_state`, `read_grid`, `hud`, `click_cell`,
  `cell_geometry`, `wait_idle`, `wait_quiet`, `settle`, `largest_group`, `check_invariants`.
- `wait_idle`/`settle`/`wait_quiet` sleep instead of polling tightly.
- The game exposes `window.samegame` (test hook) so state can be read without sampling pixels.
- Pixel checks need the pointer off the board and the board quiet — a hover highlight, a live
  particle, or the group badge can sit on a sample point.
- The tab must be foregrounded (`bring_to_front`), otherwise Chrome throttles
  `requestAnimationFrame` and the render loop stalls.

## License

[MIT](LICENSE) — the code is yours, use, modify and redistribute freely.

The game mechanics (groups of 2+, gravity, `n × (n − 1)`, clear bonus) are public domain as game
rules — the license covers this repo's original implementation. The genre is known as
SameGame / Clickomania / Tapujito / Same Color.

Live: https://bazoocaze.github.io/samegame/
