#!/usr/bin/env python3
"""Derive the offline installer request set from an immutable Calamares tree.

This tool performs no network I/O. The caller must mount the exact tree named by
its SourceLock at --calamares-root and the pipeline repository at --repo-root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

SELECTED_GROUPS = {
    "CachyOS required (hidden)",
    "CachyOS Packages",
    "CachyOS shell configuration",
    "Base-devel + Common packages",
    "LXQT-Desktop",
    "Firefox and language package",
}

PACSTRAP_RELATIVE = Path("src/modules/pacstrap/pacstrap.conf")
NETINSTALL_RELATIVE = Path("src/modules/netinstall/netinstall.yaml")
LOCAL_MANIFESTS = (
    Path("manifests/offline-extras.txt"),
    Path("manifests/repo-defaults.txt"),
)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def read_yaml(path: Path) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    return raw, yaml.safe_load(raw)


def collect_node(node: dict[str, Any], out: list[str]) -> None:
    for package in node.get("packages", []) or []:
        package = str(package).strip()
        if package and "$" not in package:
            out.append(package)

    for subgroup in node.get("subgroups", []) or []:
        if subgroup.get("selected", True):
            collect_node(subgroup, out)


def read_manifest(path: Path) -> tuple[bytes, list[str]]:
    raw = path.read_bytes()
    packages: list[str] = []
    for source_line in raw.decode("utf-8").splitlines():
        line = source_line.split("#", 1)[0].strip()
        if line:
            packages.append(line)
    return raw, packages


def derive(calamares_root: Path, repo_root: Path, output_dir: Path) -> None:
    pacstrap_path = calamares_root / PACSTRAP_RELATIVE
    netinstall_path = calamares_root / NETINSTALL_RELATIVE
    pacstrap_raw, pacstrap = read_yaml(pacstrap_path)
    netinstall_raw, netinstall = read_yaml(netinstall_path)

    if not isinstance(pacstrap, dict) or not isinstance(pacstrap.get("basePackages"), list):
        raise SystemExit("locked pacstrap.conf has no basePackages list")
    if not isinstance(netinstall, list):
        raise SystemExit("locked netinstall.yaml is not a group list")

    packages: list[str] = [str(package).strip() for package in pacstrap["basePackages"]]
    packages = [package for package in packages if package and "$" not in package]

    found: set[str] = set()
    for group in netinstall:
        if not isinstance(group, dict):
            continue
        name = group.get("name")
        if name in SELECTED_GROUPS:
            found.add(str(name))
            collect_node(group, packages)

    missing = SELECTED_GROUPS - found
    if missing:
        raise SystemExit(f"Expected installer groups not found in locked source: {sorted(missing)}")

    manifest_evidence: dict[str, str] = {}
    for relative in LOCAL_MANIFESTS:
        path = repo_root / relative
        raw, local_packages = read_manifest(path)
        packages.extend(local_packages)
        manifest_evidence[str(relative)] = sha256_bytes(raw)

    unique = sorted(dict.fromkeys(packages), key=str.casefold)
    if not unique:
        raise SystemExit("locked installer inputs produced no package requests")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "top-level-packages.txt").write_text(
        "\n".join(unique) + "\n",
        encoding="utf-8",
    )

    source_manifest = {
        "calamares_inputs": {
            str(PACSTRAP_RELATIVE): sha256_bytes(pacstrap_raw),
            str(NETINSTALL_RELATIVE): sha256_bytes(netinstall_raw),
        },
        "selected_groups": sorted(SELECTED_GROUPS),
        "local_manifests": manifest_evidence,
        "top_level_package_count": len(unique),
        "network_fetches": 0,
    }
    (output_dir / "source-manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Derived {len(unique)} top-level package/group names from locked inputs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calamares-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    derive(args.calamares_root, args.repo_root, args.output_dir)


if __name__ == "__main__":
    main()
