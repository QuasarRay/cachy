#!/usr/bin/env python3
from __future__ import annotations

import glob
import sys
from pathlib import Path, PurePosixPath

if len(sys.argv) not in {2, 3}:
    raise SystemExit("usage: verify_pacman_includes.py PACMAN_CONF [ROOT]")

config = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else Path("/")
if not config.is_file():
    raise SystemExit(f"pacman configuration does not exist: {config}")
if not root.is_dir():
    raise SystemExit(f"include root does not exist: {root}")

patterns: list[str] = []
for number, raw in enumerate(config.read_text(encoding="utf-8").splitlines(), start=1):
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        continue
    key, separator, value = stripped.partition("=")
    if separator and key.strip().lower() == "include":
        pattern = value.strip()
        if not pattern:
            raise SystemExit(f"empty Include value at {config}:{number}")
        if not PurePosixPath(pattern).is_absolute():
            raise SystemExit(
                f"relative pacman Include is not allowed at {config}:{number}: {pattern}"
            )
        if pattern not in patterns:
            patterns.append(pattern)

if not patterns:
    raise SystemExit(f"pacman configuration contains no Include directives: {config}")

for pattern in patterns:
    host_pattern = str(root / pattern.lstrip("/"))
    matches = sorted(Path(path) for path in glob.glob(host_pattern))
    if not matches:
        raise SystemExit(f"pacman Include has no matching file: {pattern}")
    empty = [path for path in matches if not path.is_file() or path.stat().st_size == 0]
    if empty:
        raise SystemExit(
            f"pacman Include resolves to missing/empty input(s): {pattern}: "
            + ", ".join(str(path) for path in empty)
        )
    print(f"Include OK: {pattern} -> {', '.join(str(path) for path in matches)}")

print(f"Verified {len(patterns)} unique pacman Include path(s)")
