#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED = (
    "amnezia-vpn-offline",
    "sing-box",
    "tor-browser-offline",
    "visual-studio-code-offline",
    "windscribe-cli",
    "xray-offline",
)


def pkginfo(path: Path) -> dict[str, str]:
    completed = subprocess.run(
        ["bsdtar", "-xOf", str(path), ".PKGINFO"],
        check=True,
        capture_output=True,
        text=True,
    )
    result: dict[str, str] = {}
    for raw in completed.stdout.splitlines():
        key, sep, value = raw.partition(" = ")
        if sep and key in {"pkgname", "pkgver", "arch"} and key not in result:
            result[key] = value.strip()
    missing = {"pkgname", "pkgver", "arch"} - result.keys()
    if missing:
        raise SystemExit(f"{path.name}: .PKGINFO missing {sorted(missing)}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: normalize_external_packages.py RAW_DIR NORMALIZED_DIR")

    raw_dir = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    if not raw_dir.is_dir():
        raise SystemExit(f"raw package directory does not exist: {raw_dir}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    selected: dict[str, tuple[Path, dict[str, str]]] = {}
    ignored_debug: list[dict[str, str]] = []
    unexpected: list[str] = []

    for package in sorted(raw_dir.glob("*.pkg.tar.zst")):
        info = pkginfo(package)
        name = info["pkgname"]
        if name.endswith("-debug"):
            ignored_debug.append(
                {"pkgname": name, "pkgver": info["pkgver"], "filename": package.name}
            )
            continue
        if name not in EXPECTED:
            unexpected.append(f"{name} ({package.name})")
            continue
        if name in selected:
            previous = selected[name][0].name
            raise SystemExit(
                f"duplicate intended SoftwarePackage output for {name}: {previous}, {package.name}"
            )
        selected[name] = (package, info)

    if unexpected:
        raise SystemExit(f"unexpected non-debug external packages: {unexpected}")

    missing = sorted(set(EXPECTED) - selected.keys())
    if missing:
        raise SystemExit(f"missing intended external packages: {missing}")
    if len(selected) != len(EXPECTED):
        raise SystemExit(
            f"expected exactly {len(EXPECTED)} intended package identities, got {len(selected)}"
        )

    manifest: list[dict[str, object]] = []
    checksum_lines: list[str] = []
    for name in EXPECTED:
        source, info = selected[name]
        destination = out_dir / source.name
        shutil.copy2(source, destination)
        digest = sha256(destination)
        size = destination.stat().st_size
        manifest.append(
            {
                "pkgname": name,
                "pkgver": info["pkgver"],
                "arch": info["arch"],
                "filename": destination.name,
                "size_bytes": size,
                "sha256": f"sha256:{digest}",
            }
        )
        checksum_lines.append(f"{digest}  {destination.name}")

    (out_dir / "EXTERNAL-SHA256SUMS").write_text("\n".join(checksum_lines) + "\n")
    (out_dir / "SOFTWARE-PACKAGES.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "expected_package_names": list(EXPECTED),
                "packages": manifest,
                "ignored_split_debug_packages": ignored_debug,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(f"Normalized {len(manifest)} intended external package outputs")
    if ignored_debug:
        print(f"Ignored {len(ignored_debug)} makepkg split debug package(s)")
        for item in ignored_debug:
            print(f"  {item['pkgname']}: {item['filename']}")


if __name__ == "__main__":
    main()
