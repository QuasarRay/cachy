#!/usr/bin/env python3
"""Configure CachyOS x86-64-v4 and multilib repositories in pacman.conf.

The target machine is x86-64-v4. CachyOS also ships some packages only from
its generic repository with lower x86-64 microarchitecture declarations.
An x86-64-v4 CPU is backward-compatible with v3/v2/base, so the resolver must
accept the full hierarchy while keeping the v4 repositories highest priority.
We deliberately do not use CI-host CPU auto-detection.
"""

from pathlib import Path
import re
import sys

path = Path(sys.argv[1] if len(sys.argv) > 1 else "/etc/pacman.conf")
lines = path.read_text(encoding="utf-8").splitlines()

managed_repo = re.compile(
    r"^\[(?:cachyos(?:-(?:(?:core|extra)-)?(?:v3|v4|znver4))?|multilib)\]$"
)

out: list[str] = []
i = 0
while i < len(lines):
    if managed_repo.match(lines[i].strip()):
        i += 1
        while i < len(lines) and not lines[i].lstrip().startswith("["):
            i += 1
        continue
    line = lines[i]
    if line.strip().startswith("Architecture"):
        line = "Architecture = x86_64 x86_64_v2 x86_64_v3 x86_64_v4"
    out.append(line)
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
    "[cachyos]",
    "Include = /etc/pacman.d/cachyos-mirrorlist",
    "",
]

for index, line in enumerate(out):
    if line.strip() == "[core]":
        out[index:index] = insert
        break
else:
    raise SystemExit("[core] repository not found in pacman.conf")

out.extend([
    "",
    "[multilib]",
    "Include = /etc/pacman.d/mirrorlist",
])

path.write_text("\n".join(out) + "\n", encoding="utf-8")
