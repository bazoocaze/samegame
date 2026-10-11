#!/usr/bin/env python3
"""Black-box browser test for the SameGame clone (reuses tests/browser_lib.py).

    uv run python tests/test_game.py

Checks: scoring n*(n-1), gravity, column compaction, end-of-game overlay,
undo, shuffle, hint, best-score persistence, that the rendered canvas
matches the game state, and that an idle board triggers no render at all.
Sleeps between reads keep the CPU idle.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_lib import (  # noqa: E402
    open_game, read_state, read_grid, hud, click_cell, settle, wait_idle, wait_quiet, cell_geometry,
    largest_group, check_invariants, show_grid,
)

ROOT = Path(__file__).resolve().parent.parent


def main():
    page = open_game()
    fails = []

    s = wait_idle(page)
    cols, rows = s["cols"], s["rows"]
    total = s["blocks"]
    geom = cell_geometry(page)
    print(f"board {cols}x{rows}, {total} blocks, cell={round(geom['cell'])}px")

    expected, popped, score_before_last, last_group = 0, 0, 0, 0
    for i in range(120):
        best = largest_group(s["grid"])
        if len(best) < 2:
            break
        score_before_last, last_group = expected, len(best)
        expected += last_group * (last_group - 1)
        popped += last_group

        r, c = best[0]
        click_cell(page, r, c, geom)
        settle(page)
        s = wait_idle(page)

        try:
            check_invariants(s["grid"], f"move {i + 1}")
        except AssertionError as e:
            fails.append(str(e))
            show_grid(s["grid"])
            break
        h = hud(page)
        if int(h["score"]) != expected:
            fails.append(f"move {i + 1}: score {h['score']} != {expected}")
        if int(h["left"]) != total - popped:
            fails.append(f"move {i + 1}: blocks {h['left']} != {total - popped}")
        if int(h["moves"]) != i + 1:
            fails.append(f"move {i + 1}: moves {h['moves']} != {i + 1}")
        time.sleep(0.05)

    h = hud(page)
    bonus = 2000 if s["blocks"] == 0 else 0
    if int(h["score"]) != expected + bonus:
        fails.append(f"final score {h['score']} != {expected + bonus}")
    if not h["overlay"]:
        fails.append("end-of-game overlay not shown")
    print(f"finished: score={h['score']} moves={h['moves']} left={h['left']} "
          f"overlay={h['overlay']} ({h['overlayText']})")

    # undo restores the previous score and block count
    page.evaluate("() => document.getElementById('btnUndo').click()")
    settle(page)
    s = wait_idle(page)
    h = hud(page)
    if int(h["score"]) != score_before_last:
        fails.append(f"undo score {h['score']} != {score_before_last}")
    if int(h["left"]) != total - popped + last_group:
        fails.append(f"undo blocks {h['left']} != {total - popped + last_group}")
    try:
        check_invariants(s["grid"], "undo")
    except AssertionError as e:
        fails.append(str(e))
    print(f"undo: score -> {h['score']}, blocks -> {h['left']}")

    # hint reports a playable group
    page.evaluate("() => document.getElementById('btnHint').click()")
    page.wait_for_timeout(300)
    line = hud(page)["hintline"]
    if "Best group" not in line:
        fails.append(f"hint produced no group: {line!r}")
    print("hint:", line)

    # shuffle permutes colours but keeps the multiset
    before = sorted(v for row in s["grid"] for v in row if v is not None)
    page.evaluate("() => document.getElementById('btnShuffle').click()")
    settle(page)
    s = wait_idle(page)
    after = sorted(v for row in s["grid"] for v in row if v is not None)
    if before != after:
        fails.append("shuffle changed the colour multiset")
    try:
        check_invariants(s["grid"], "shuffle")
    except AssertionError as e:
        fails.append(str(e))
    print("shuffle: multiset preserved")

    # the canvas must render exactly what the game state holds.
    # The pointer must be off the board: a hover highlight, a live particle, or the
    # group badge (drawn over the group centroid) can sit on a sample point and read
    # as a colour that matches no palette entry.
    page.mouse.move(0, 0)
    s = wait_quiet(page)
    px = read_grid(page)
    mismatch = sum(
        1 for r in range(rows) for c in range(cols)
        if px["grid"][r][c] != s["grid"][r][c]
    )
    if mismatch:
        fails.append(f"render mismatch: {mismatch} cells differ from state")
    print(f"render matches state: {not mismatch}")

    # render-on-change: an idle board must draw nothing at all.
    # clearRect runs once per render(), so counting it counts rendered frames.
    page.evaluate("""() => {
      const ctx = document.getElementById('board').getContext('2d');
      const orig = ctx.clearRect;
      window.__renders = 0;
      ctx.clearRect = function (...a) { window.__renders++; return orig.apply(this, a); };
    }""")
    page.mouse.move(0, 0)  # pointer off the board, so no hover animation to draw
    s = wait_quiet(page)   # nothing left to draw: no particles, popups, hint, hover
    page.evaluate("() => { window.__renders = 0; }")
    page.wait_for_timeout(1000)
    idle_renders = page.evaluate("() => window.__renders")
    if idle_renders:
        fails.append(f"idle board rendered {idle_renders} times in 1s (expected 0)")
    g = largest_group(s["grid"])
    if len(g) >= 2:
        click_cell(page, g[0][0], g[0][1], geom)
        page.wait_for_timeout(600)
        after = page.evaluate("() => window.__renders")
        if after <= idle_renders:
            fails.append("a move produced no render")
        print(f"render-on-change: {idle_renders} renders in 1s quiet idle, {after} after a move")
    else:
        print(f"render-on-change: {idle_renders} renders in 1s quiet idle (no playable group to click)")

    # best score persists across a reload
    best_before = hud(page)["best"]
    page.reload()
    page.bring_to_front()
    page.wait_for_timeout(1200)
    if hud(page)["best"] != best_before:
        fails.append(f"best score not persisted ({best_before} -> {hud(page)['best']})")
    print("best persisted:", best_before)

    page.screenshot(path=str(ROOT / "tests" / "screenshot.png"))
    print("\n" + ("FAIL" if fails else "ALL CHECKS PASSED"))
    for f in fails:
        print(" -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
