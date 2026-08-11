#!/usr/bin/env python3
"""Build the reviewable CachyOS LXQt top-level package manifest.

The authoritative installer inputs are fetched from CachyOS's current
`cachyos` branch. Package payloads are not downloaded by this script.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import yaml

PACSTRAP_URL = (
    "https://raw.githubusercontent.com/CachyOS/cachyos-calamares/"
    "cachyos/src/modules/pacstrap/pacstrap.conf"
)
NETINSTALL_URL = (
    "https://raw.githubusercontent.com/CachyOS/cachyos-calamares/"
    "cachyos/src/modules/netinstall/netinstall.yaml"
)

SELECTED_GROUPS = {
    "CachyOS required (hidden)",
    "CachyOS Packages",
    "CachyOS shell configuration",
    "Base-devel + Common packages",
    "LXQT-Desktop",
    "Firefox and language package",
}


def fetch(url: str) -> bytes:
    with urlopen(url, timeout=60) as response:
        return response.read()


def collect_node(node: dict, out: list[str]) -> None:
    for package in node.get("packages", []) or []:
        package = str(package).strip()
        # Calamares substitutes variables such as $LOCALE at install time.
        # Hardware/build-specific concrete replacements live in offline-extras.
        if package and "$" not in package:
            out.append(package)

    for subgroup in node.get("subgroups", []) or []:
        # Subgroups explicitly disabled by default are optional and are not part
        # of the baseline cache. Selected/default subgroups are included.
        if subgroup.get("selected", True):
            collect_node(subgroup, out)


def read_extras(path: Path) -> list[str]:
    packages: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            packages.append(line)
    return packages


def main() -> None:
    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)

    pacstrap_raw = fetch(PACSTRAP_URL)
    netinstall_raw = fetch(NETINSTALL_URL)
    pacstrap = yaml.safe_load(pacstrap_raw)
    netinstall = yaml.safe_load(netinstall_raw)

    packages: list[str] = list(pacstrap["basePackages"])
    found: set[str] = set()

    for group in netinstall:
        name = group.get("name")
        if name in SELECTED_GROUPS:
            found.add(name)
            collect_node(group, packages)

    missing = SELECTED_GROUPS - found
    if missing:
        raise SystemExit(f"Expected installer groups not found: {sorted(missing)}")

    packages.extend(read_extras(Path("manifests/offline-extras.txt")))

    # Stable order makes reviews and cache keys deterministic.
    unique = sorted(dict.fromkeys(packages), key=str.casefold)
    Path("out/top-level-packages.txt").write_text(
        "\n".join(unique) + "\n", encoding="utf-8"
    )

    source_manifest = {
        "pacstrap_url": PACSTRAP_URL,
        "pacstrap_sha256": hashlib.sha256(pacstrap_raw).hexdigest(),
        "netinstall_url": NETINSTALL_URL,
        "netinstall_sha256": hashlib.sha256(netinstall_raw).hexdigest(),
        "selected_groups": sorted(SELECTED_GROUPS),
        "top_level_package_count": len(unique),
    }
    Path("out/source-manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Collected {len(unique)} top-level package/group names")


if __name__ == "__main__":
    main()
