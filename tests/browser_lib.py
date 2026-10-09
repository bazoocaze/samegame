"""Reusable browser helpers for the SameGame test scripts.

Connects to the already-installed Chrome over CDP through the browser-control
skill (no Playwright browser download needed), opens index.html, and exposes
black-box helpers that read the board from the canvas pixels.

    from tests.browser_lib import open_game
    page = open_game()
    grid = read_grid_stable(page)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = f"file://{ROOT / 'index.html'}"
TAB = "samegame"

sys.path.insert(0, str(Path.home() / ".agents/skills/browser-control"))
from lib import generic_open  # noqa: E402

PALETTE = ["#ff5f6d", "#f7b32b", "#3ddc97", "#4aa8ff", "#b388ff", "#2fd4c8"]

READ_GRID = """() => {
  const c = document.getElementById('board');
  const ctx = c.getContext('2d');
  const w = parseFloat(c.style.width), h = parseFloat(c.style.height);
  const pad = 12;
  const [cols, rows] = document.getElementById('selSize').value.split(',').map(Number);
  const cell = (w - pad * 2) / cols;
  const dpr = c.width / w;
  const pal = %s;
  const nearest = (r, g, b) => {
    let best = -1, bd = 1e9;
    for (let i = 0; i < pal.length; i++) {
      const p = pal[i];
      const pr = parseInt(p.slice(1,3),16), pg = parseInt(p.slice(3,5),16), pb = parseInt(p.slice(5,7),16);
      const d = (pr-r)*(pr-r) + (pg-g)*(pg-g) + (pb-b)*(pb-b);
      if (d < bd) { bd = d; best = i; }
    }
    return bd < 9000 ? best : null;
  };
  const grid = [];
  for (let r = 0; r < rows; r++) {
    const row = [];
    for (let c2 = 0; c2 < cols; c2++) {
      const x = Math.round((pad + (c2 + 0.5) * cell) * dpr);
      const y = Math.round((pad + (r + 0.5) * cell) * dpr);
      const d = ctx.getImageData(x, y, 1, 1).data;
      row.push(nearest(d[0], d[1], d[2]));
    }
    grid.push(row);
  }
  return { grid, cols, rows, cell, pad, dpr, cssW: w, cssH: h };
}""" % (PALETTE,)

HUD = """() => ({
  score: document.getElementById('score').textContent,
  best: document.getElementById('best').textContent,
  moves: document.getElementById('moves').textContent,
  left: document.getElementById('left').textContent,
  overlay: document.getElementById('overlay').classList.contains('show'),
  overlayText: document.getElementById('ovText').textContent,
  hintline: document.getElementById('hintline').textContent,
})"""


def open_game(name=TAB, fresh=True):
    """Open (or reuse) the game tab. The tab must be foregrounded, otherwise
    Chrome throttles requestAnimationFrame and the render loop stalls."""
    page = generic_open(URL, name=name)
    page.bring_to_front()
    page.wait_for_selector("#board")
    if fresh:
        page.reload()
        page.bring_to_front()
    page.wait_for_timeout(1200)  # spawn animation
    return page

def settle(page, ms=520):
    """Wait for the pop (170ms) + settle (280ms) animations to finish.
    A real sleep keeps the CPU idle instead of hammering the canvas."""
    page.wait_for_timeout(ms)


STATE = """() => {
  const g = window.samegame;
  const grid = g.state.grid.map(row => row.map(c => c ? c.color : null));
  return { grid, cols: g.cfg.cols, rows: g.cfg.rows, phase: g.state.phase,
           score: g.state.score, moves: g.state.moves, over: g.state.over,
           blocks: g.blocksLeft() };
}"""


def read_state(page):
    """Authoritative board from the game itself — cheap, no pixel sampling."""
    return page.evaluate(STATE)


def wait_idle(page, timeout_ms=6000, poll_ms=120):
    """Wait until the game reaches its idle phase (animations applied).
    Polls sparsely so it does not spin the CPU."""
    deadline = timeout_ms
    while deadline > 0:
        s = read_state(page)
        if s["phase"] == "idle":
            return s
        page.wait_for_timeout(poll_ms)
        deadline -= poll_ms
    return read_state(page)


def read_grid(page):
    return page.evaluate(READ_GRID)


def hud(page):
    return page.evaluate(HUD)


def read_grid_stable(page, tries=6, quiet_ms=250):
    """Poll the canvas until two consecutive reads match (animations settled).
    Reads are the expensive part, so the poll is sparse on purpose."""
    prev = read_grid(page)
    for _ in range(tries):
        page.wait_for_timeout(quiet_ms)
        cur = read_grid(page)
        if cur["grid"] == prev:
            return cur
        prev = cur
    return prev


def board_rect(page):
    return page.evaluate(
        "() => { const b = document.getElementById('board').getBoundingClientRect();"
        " return { left: b.left, top: b.top, width: b.width, height: b.height }; }"
    )


def cell_geometry(page):
    """Board geometry from the DOM (cheap — no canvas sampling)."""
    rect = board_rect(page)
    cols, rows = page.evaluate(
        "() => document.getElementById('selSize').value.split(',').map(Number)"
    )
    pad = 12
    return {"pad": pad, "cell": (rect["width"] - pad * 2) / cols, "cols": cols, "rows": rows, "rect": rect}


def click_cell(page, r, c, geom=None):
    geom = geom or cell_geometry(page)
    x = geom["rect"]["left"] + geom["pad"] + (c + 0.5) * geom["cell"]
    y = geom["rect"]["top"] + geom["pad"] + (r + 0.5) * geom["cell"]
    page.mouse.click(x, y)
    return page


def find_group(grid, r, c):
    color = grid[r][c]
    seen, stack, out = {f"{r}:{c}"}, [(r, c)], []
    while stack:
        cr, cc = stack.pop()
        out.append((cr, cc))
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < len(grid) and 0 <= nc < len(grid[0])):
                continue
            if grid[nr][nc] == color and f"{nr}:{nc}" not in seen:
                seen.add(f"{nr}:{nc}")
                stack.append((nr, nc))
    return out


def largest_group(grid):
    return max(
        (find_group(grid, r, c)
         for r in range(len(grid)) for c in range(len(grid[0]))
         if grid[r][c] is not None),
        key=len, default=[],
    )


def check_invariants(grid, tag="board"):
    """SameGame invariants: blocks rest on the floor or on another block,
    and no empty column may sit to the left of a filled one."""
    rows, cols = len(grid), len(grid[0])
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] is not None and r + 1 < rows and grid[r + 1][c] is None:
                raise AssertionError(f"{tag}: floating block at ({r},{c})")
    empty_seen = False
    for c in range(cols):
        if not any(grid[r][c] is not None for r in range(rows)):
            empty_seen = True
        elif empty_seen:
            raise AssertionError(f"{tag}: empty column {c} before a filled one")
    return True


def show_grid(grid):
    for row in grid:
        print(" ".join("." if v is None else str(v) for v in row))
