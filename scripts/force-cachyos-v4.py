#!/usr/bin/env python3
"""Configure CachyOS x86-64-v4 and multilib repositories in pacman.conf.

The build target is x86-64-v4. This deliberately does not use the repository
bootstrap script's host-CPU auto-detection because GitHub's runner CPU is not
the target machine. The finished ISO will still perform a target compatibility
check before installation.
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

# Multilib should follow the normal Arch core/extra repositories. Appending it
# is sufficient for dependency resolution and matches the repository source.
out.extend([
    "",
    "[multilib]",
    "Include = /etc/pacman.d/mirrorlist",
])

path.write_text("\n".join(out) + "\n", encoding="utf-8")
