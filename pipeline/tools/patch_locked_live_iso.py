#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_locked_live_iso.py LIVE_ISO_SOURCE_ROOT")

root = Path(sys.argv[1]).resolve()
util_iso = root / "util-iso.sh"
if not util_iso.is_file():
    raise SystemExit(f"missing locked live ISO util-iso.sh: {util_iso}")

text = util_iso.read_text()
pattern = re.compile(
    r"fetch_cachyos_mirrorlist\(\) \{\n.*?\n\}\n\nchange_grub_version",
    re.DOTALL,
)
replacement = """fetch_cachyos_mirrorlist() {
    mkdir -p ${src_dir}/archiso/airootfs/etc/pacman.d
    # The build host installs a versioned CachyOS mirrorlist package before
    # entering the locked live-ISO source. Copy that exact local input rather
    # than fetching CachyOS-PKGBUILDS/master during image construction.
    test -s /etc/pacman.d/cachyos-mirrorlist
    cp /etc/pacman.d/cachyos-mirrorlist ${src_dir}/archiso/airootfs/etc/pacman.d/cachyos-mirrorlist
}

change_grub_version"""
updated, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(
        "locked live ISO mirrorlist function changed; refusing an ambiguous reproducibility patch"
    )
if "CachyOS-PKGBUILDS/raw/master" in updated:
    raise SystemExit("moving CachyOS mirrorlist fetch remains after patch")
util_iso.write_text(updated)

print("Patched locked live ISO to use the installed versioned CachyOS mirrorlist")
