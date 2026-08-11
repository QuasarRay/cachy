#!/usr/bin/env python3
"""Force CachyOS x86-64-v4 optimized repositories in pacman.conf.

The target laptop is an Intel Core i7-11800H (Tiger Lake), which is an
AVX-512-capable 11th-gen CPU. CachyOS documents x86-64-v4 as the appropriate
optimized repository tier when the runtime loader reports x86-64-v4 support.
The ISO will still perform that compatibility check before installation.
"""

from pathlib import Path
import re
import sys

path = Path(sys.argv[1] if len(sys.argv) > 1 else "/etc/pacman.conf")
lines = path.read_text(encoding="utf-8").splitlines()

optimized = re.compile(
    r"^\[cachyos(?:-(?:core-|extra-)?(?:v3|v4|znver4))\]$"
)

out: list[str] = []
i = 0
while i < len(lines):
    if optimized.match(lines[i].strip()):
        i += 1
        while i < len(lines) and not lines[i].lstrip().startswith("["):
            i += 1
        continue
    out.append(lines[i])
    i += 1

insert = [
    "[cachyos-v4]",
    "Include = /etc/pacman.d/cachyos-v4-mirrorlist",
    "",
    "[cachyos-core-v4]",
    "Include = /etc/pacman.d/cachyos-v4-mirrorlist",
    "",
    "[cachyos-extra-v4]",
    "Include = /etc/pacman.d/cachyos-v4-mirrorlist",
    "",
]

for index, line in enumerate(out):
    if line.strip() == "[cachyos]":
        out[index:index] = insert
        break
else:
    raise SystemExit("[cachyos] repository was not installed by bootstrap script")

path.write_text("\n".join(out) + "\n", encoding="utf-8")
