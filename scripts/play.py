#!/usr/bin/env python3
"""Reusable playthrough script — plays the game in the browser and prints the board.

    uv run python scripts/play.py [--moves 40] [--delay 0.4]

Reuses tests/browser_lib.py (Chrome over CDP, no Playwright browser download).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from browser_lib import open_game, read_state, hud, click_cell, largest_group, show_grid, wait_idle, cell_geometry  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves", type=int, default=40)
    ap.add_argument("--delay", type=float, default=0.4, help="sleep between moves (seconds)")
    ap.add_argument("--name", default="samegame-play")
    args = ap.parse_args()

    page = open_game(name=args.name)
    s = wait_idle(page)
    geom = cell_geometry(page)

    for i in range(args.moves):
        best = largest_group(s["grid"])
        if len(best) < 2:
            break
        r, c = best[0]
        click_cell(page, r, c, geom)
        time.sleep(args.delay)
        s = wait_idle(page)
        print(f"move {i + 1}: popped {len(best)} -> score {s['score']}, blocks {s['blocks']}")
        show_grid(s["grid"])
        print()

    print("final:", hud(page))
    return 0


if __name__ == "__main__":
    sys.exit(main())
