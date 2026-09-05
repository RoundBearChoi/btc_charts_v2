#!/usr/bin/env python3
"""Rebuild src/ratio_between_coins.py from origin/main + the overlay patch.

Run from repo root:
    python src/_install_ratio_long_term.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "src" / "ratio_between_coins.py"
PATCH = REPO / "patches" / "ratio_long_term_overlay.patch"
MAIN_REF = "origin/main"


def run(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd,
        cwd=REPO,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def main() -> int:
    if not PATCH.exists():
        print(f"[ERROR] Patch not found: {PATCH}")
        return 1

    print(f"Fetching {MAIN_REF} ...")
    subprocess.run(["git", "fetch", "origin", "main"], cwd=REPO, check=False)

    print(f"Restoring {TARGET.relative_to(REPO)} from {MAIN_REF}")
    run(["git", "checkout", MAIN_REF, "--", "src/ratio_between_coins.py"])

    lines = TARGET.read_text().count("\n") + 1
    print(f"  restored line count: {lines}")
    if lines < 500:
        print("[ERROR] Restored file still looks too short. Is origin/main available?")
        return 1

    print(f"Applying {PATCH.relative_to(REPO)}")
    apply = subprocess.run(
        ["git", "apply", str(PATCH)],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        print(apply.stderr)
        print("[ERROR] git apply failed")
        return apply.returncode

    new_lines = TARGET.read_text().count("\n") + 1
    tail = "\n".join(TARGET.read_text().splitlines()[-3:])
    print(f"  patched line count: {new_lines}")
    print(f"  tail:\n{tail}")
    if "def main()" not in TARGET.read_text() or new_lines < 700:
        print("[ERROR] Patch applied but file still does not look complete")
        return 1

    print("OK. Commit with:")
    print("  git add src/ratio_between_coins.py")
    print('  git commit -m "Add light long-term SMA and peak/bottom envelope to ratio chart"')
    print("Then run:")
    print("  python src/ratio_between_coins.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
