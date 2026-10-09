#!/usr/bin/env python3
"""Reusable screenshot script for the SameGame clone.

    uv run python scripts/screenshot.py [--out tests/screenshot.png] [--moves 12]

Reuses tests/browser_lib.py (Chrome over CDP).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from browser_lib import open_game, read_state, click_cell, largest_group, wait_idle, cell_geometry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "tests" / "screenshot.png"))
    ap.add_argument("--moves", type=int, default=12)
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--name", default="samegame-shot")
    args = ap.parse_args()

    page = open_game(name=args.name)
    s = wait_idle(page)
    geom = cell_geometry(page)

    for _ in range(args.moves):
        best = largest_group(s["grid"])
        if len(best) < 2:
            break
        click_cell(page, best[0][0], best[0][1], geom)
        time.sleep(args.delay)
        s = wait_idle(page)

    # hover the biggest remaining group so the highlight shows in the shot
    best = largest_group(s["grid"])
    if len(best) >= 2:
        r, c = best[0]
        page.mouse.move(geom["rect"]["left"] + geom["pad"] + (c + 0.5) * geom["cell"],
                        geom["rect"]["top"] + geom["pad"] + (r + 0.5) * geom["cell"])
        time.sleep(0.3)

    page.screenshot(path=args.out)
    print(f"saved {args.out} (score {s['score']}, blocks {s['blocks']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
