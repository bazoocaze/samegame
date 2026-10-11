#!/usr/bin/env python3
"""Measure per-frame CPU cost of the game's render loop in an isolated Chrome instance.

Method: launch a dedicated Chrome with its own profile (so the game is the only page),
connect over CDP, and read utime+stime from /proc/<pid>/stat for the renderer process
that owns the game. No instrumentation is added to index.html.

Usage:
    uv run python scripts/cpu_measure.py                     # headful, 6s windows
    uv run python scripts/cpu_measure.py --headless          # software rasterization (inflates numbers)
    uv run python scripts/cpu_measure.py --window 10
    uv run python scripts/cpu_measure.py --experiments       # runtime-only patches, see notes

Important: headful and headless are NOT comparable. Headless rasterizes on CPU
(swiftshader), which roughly doubles the reported cost vs a real GPU-backed browser.
Always state which mode was used when quoting a number.
"""
import argparse
import os
import pathlib
import subprocess
import time

from playwright.sync_api import sync_playwright

HZ = os.sysconf("SC_CLK_TCK")


def renderer_cpu(profile: str) -> dict[str, float]:
    """CPU seconds per renderer process whose cmdline mentions `profile`."""
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="ignore")
            if "--type=renderer" not in cmd or profile not in cmd:
                continue
            stat = open(f"/proc/{pid}/stat").read().split()
            out[pid] = (int(stat[13]) + int(stat[14])) / HZ
        except OSError:
            pass
    return out


def measure(profile: str, seconds: int, label: str) -> float:
    a = renderer_cpu(profile)
    time.sleep(seconds)
    b = renderer_cpu(profile)
    delta = {k: b[k] - a.get(k, 0) for k in b if b[k] - a.get(k, 0) > 0}
    total = sum(delta.values())
    pct = 100 * total / seconds
    print(f"{label}: {total:.2f} CPU-s / {seconds}s = {pct:.0f}% of a core  "
          f"{[(k, round(v, 2)) for k, v in delta.items()]}")
    return pct


def instrument(pg) -> dict:
    """Count canvas ops per frame and time the JS side of fill/gradient.
    clearRect runs once per render(), so it doubles as a rendered-frames counter."""
    pg.evaluate("""() => {
      const ctx = document.getElementById('board').getContext('2d');
      const C = {fill: 0, grad: 0, rr: 0, render: 0}, T = {fill: 0, grad: 0};
      const wrap = (name, key) => {
        const orig = ctx[name];
        ctx[name] = function (...a) {
          C[key]++;
          const t0 = performance.now();
          const r = orig.apply(this, a);
          if (key) T[key] += performance.now() - t0;
          return r;
        };
      };
      wrap('fill', 'fill');
      wrap('createLinearGradient', 'grad');
      wrap('roundRect', 'rr');
      wrap('clearRect', 'render');   // clearRect runs once per render() -> rendered frames
      window.__m = {C, T, frames: 0};
      const raf = window.requestAnimationFrame.bind(window);
      (function f() { window.__m.frames++; raf(f); })();
    }""")
    return pg.evaluate("() => ({C: window.__m.C, T: window.__m.T, frames: window.__m.frames})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="cpuref-headful")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--window", type=int, default=6, help="seconds per measurement window")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--experiments", action="store_true",
                    help="apply runtime patches to the page (does not touch index.html)")
    args = ap.parse_args()

    html = pathlib.Path(__file__).resolve().parent.parent / "index.html"
    flags = ["--no-first-run", f"--user-data-dir=/tmp/{args.profile}",
             f"--remote-debugging-port={args.port}"]
    if args.headless:
        flags.insert(1, "--headless=new")

    proc = subprocess.Popen(["google-chrome", *flags],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    time.sleep(8)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
            page = browser.contexts[0].new_page()
            page.goto(f"file://{html}")
            time.sleep(3)

            headful = "HeadlessChrome" not in page.evaluate("() => navigator.userAgent")
            print(f"mode: {'headful' if headful else 'headless'} | "
                  f"dpr: {page.evaluate('() => window.devicePixelRatio')} | "
                  f"visibility: {page.evaluate('() => document.visibilityState')}")

            measure(args.profile, args.window, "idle, foreground")

            page.mouse.move(200, 200)
            time.sleep(1)
            measure(args.profile, args.window, "hover a group")

            other = browser.contexts[0].new_page()
            other.goto("data:text/html,<h1>other tab</h1>")
            time.sleep(1)
            print(f"game tab visibility after backgrounding: "
                  f"{page.evaluate('() => document.visibilityState')}")
            measure(args.profile, args.window, "game tab backgrounded")
            other.close()

            if args.experiments:
                base = instrument(page)
                time.sleep(args.window)
                now = page.evaluate("() => ({C: window.__m.C, T: window.__m.T, frames: window.__m.frames})")
                df = now["frames"] - base["frames"]
                dr = now["C"]["render"] - base["C"]["render"]
                print(f"ops/frame: fills={(now['C']['fill'] - base['C']['fill']) / df:.0f} "
                      f"gradients={(now['C']['grad'] - base['C']['grad']) / df:.0f} "
                      f"roundRect={(now['C']['rr'] - base['C']['rr']) / df:.0f} | "
                      f"rendered frames/frame: {dr / df:.2f} | "
                      f"JS: fill {(now['T']['fill'] - base['T']['fill']) / args.window * 1000:.0f} us/s, "
                      f"gradients {(now['T']['grad'] - base['T']['grad']) / args.window * 1000:.0f} us/s, "
                      f"fps={df / args.window:.0f}")

                # A/B in the same page: force a render every frame, i.e. bypass the dirty
                # flag. The gap against the idle baseline is what the flag saves.
                page.evaluate("""() => {
                  const raf = window.requestAnimationFrame.bind(window);
                  (function f() { window.samegame.markDirty(); raf(f); })();
                }""")
                time.sleep(2)
                measure(args.profile, args.window, "idle, render forced every frame")

            browser.close()
    finally:
        os.killpg(proc.pid, 15)


if __name__ == "__main__":
    main()
