#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path


def parse_desc(path: Path) -> dict[str, str]:
    lines = path.read_text(errors="strict").splitlines()
    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("%") and line.endswith("%") and i + 1 < len(lines):
            key = line.strip("%")
            value = lines[i + 1].strip()
            if value:
                result[key] = value
            i += 2
            continue
        i += 1
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_sync_db(db: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["bsdtar", "-xf", str(db), "-C", str(destination)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify cached Arch/CachyOS package bytes against SHA256SUM values "
            "stored in the Pacman sync databases used to resolve/download them."
        )
    )
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--db-dir", required=True, type=Path)
    parser.add_argument("--expected-count", required=True, type=int)
    parser.add_argument("--upstream-sums", required=True, type=Path)
    parser.add_argument("--report-json", required=True, type=Path)
    args = parser.parse_args()

    cache_dir = args.cache_dir.resolve()
    sync_dir = (args.db_dir.resolve() / "sync")
    packages = sorted(cache_dir.glob("*.pkg.tar.zst"))
    sync_dbs = sorted(sync_dir.glob("*.db"))

    if len(packages) != args.expected_count:
        raise SystemExit(
            f"cached package count mismatch: expected {args.expected_count}, got {len(packages)}"
        )
    if not sync_dbs:
        raise SystemExit(f"no Pacman sync databases found under {sync_dir}")
    if shutil.which("bsdtar") is None:
        raise SystemExit("bsdtar is required")

    authoritative: dict[str, str] = {}
    sources: dict[str, list[dict[str, str]]] = defaultdict(list)
    sync_db_sha256: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="syncdb-verify-") as tmp:
        tmp_root = Path(tmp)
        for db in sync_dbs:
            repo = db.stem
            sync_db_sha256[db.name] = sha256(db)
            repo_root = tmp_root / repo
            extract_sync_db(db, repo_root)
            for desc_path in sorted(repo_root.rglob("desc")):
                desc = parse_desc(desc_path)
                filename = desc.get("FILENAME")
                expected_sha = desc.get("SHA256SUM")
                if not filename or not expected_sha:
                    continue
                expected_sha = expected_sha.lower()
                if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
                    raise SystemExit(
                        f"invalid SHA256SUM in {repo} metadata for {filename}: {expected_sha!r}"
                    )
                previous = authoritative.get(filename)
                if previous is not None and previous != expected_sha:
                    raise SystemExit(
                        "conflicting upstream hashes for the same filename: "
                        f"{filename}: {previous} vs {expected_sha}"
                    )
                authoritative[filename] = expected_sha
                sources[filename].append(
                    {
                        "repository": repo,
                        "name": desc.get("NAME", ""),
                        "version": desc.get("VERSION", ""),
                        "sha256": expected_sha,
                    }
                )

    verified: list[dict[str, object]] = []
    upstream_sum_lines: list[str] = []
    missing: list[str] = []
    mismatches: list[dict[str, str]] = []

    for package in packages:
        expected = authoritative.get(package.name)
        if expected is None:
            missing.append(package.name)
            continue
        actual = sha256(package)
        if actual != expected:
            mismatches.append(
                {
                    "filename": package.name,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                }
            )
            continue
        upstream_sum_lines.append(f"{expected}  {package.name}")
        verified.append(
            {
                "filename": package.name,
                "sha256": actual,
                "size_bytes": package.stat().st_size,
                "upstream_records": sources[package.name],
            }
        )

    if missing or mismatches:
        details = {
            "missing_from_saved_sync_metadata": missing[:50],
            "hash_mismatches": mismatches[:50],
        }
        raise SystemExit("upstream package verification failed: " + json.dumps(details, sort_keys=True))

    if len(verified) != args.expected_count:
        raise SystemExit(
            f"verified package count mismatch: expected {args.expected_count}, got {len(verified)}"
        )

    args.upstream_sums.parent.mkdir(parents=True, exist_ok=True)
    args.upstream_sums.write_text("\n".join(upstream_sum_lines) + "\n")

    report = {
        "schema": 1,
        "verification_method": (
            "sha256(cached package bytes) == %SHA256SUM% from the saved Pacman sync "
            "database used by the package-resolution/download checkpoint"
        ),
        "expected_package_count": args.expected_count,
        "verified_package_count": len(verified),
        "all_cached_packages_match_saved_upstream_repository_hashes": True,
        "sync_database_count": len(sync_dbs),
        "sync_database_sha256": sync_db_sha256,
        "packages": verified,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(
        f"Verified {len(verified)} cached packages against SHA-256 values from "
        f"{len(sync_dbs)} saved Pacman sync database(s)"
    )


if __name__ == "__main__":
    main()
