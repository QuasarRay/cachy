#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


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
    subprocess.run(["bsdtar", "-xf", str(db), "-C", str(destination)], check=True)


def load_resolution_manifest(path: Path, expected_count: int) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen_filenames: dict[str, dict[str, object]] = {}
    for line_number, raw in enumerate(path.read_text(errors="strict").splitlines(), start=1):
        if not raw.strip():
            continue
        fields = raw.split("\t")
        if len(fields) != 5:
            raise SystemExit(
                f"resolution manifest line {line_number} must have 5 tab-separated fields, got {len(fields)}"
            )
        name, version, repository, size_text, url = fields
        try:
            size_bytes = int(size_text)
        except ValueError as exc:
            raise SystemExit(
                f"resolution manifest line {line_number} has invalid size: {size_text!r}"
            ) from exc
        filename = unquote(Path(urlsplit(url).path).name)
        if not all((name, version, repository, url, filename)):
            raise SystemExit(f"resolution manifest line {line_number} contains an empty required field")
        record: dict[str, object] = {
            "name": name,
            "version": version,
            "repository": repository,
            "size_bytes": size_bytes,
            "url": url,
            "filename": filename,
        }
        previous = seen_filenames.get(filename)
        if previous is not None:
            raise SystemExit(
                "resolution manifest selects the same package filename more than once: "
                f"{filename}: {previous!r} vs {record!r}"
            )
        seen_filenames[filename] = record
        records.append(record)

    if len(records) != expected_count:
        raise SystemExit(
            f"resolution manifest count mismatch: expected {expected_count}, got {len(records)}"
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify cached Arch/CachyOS package bytes against SHA256SUM values from "
            "the exact Pacman repository selected by the original resolution manifest."
        )
    )
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--db-dir", required=True, type=Path)
    parser.add_argument("--resolved-packages", required=True, type=Path)
    parser.add_argument("--expected-count", required=True, type=int)
    parser.add_argument("--upstream-sums", required=True, type=Path)
    parser.add_argument("--report-json", required=True, type=Path)
    args = parser.parse_args()

    cache_dir = args.cache_dir.resolve()
    sync_dir = args.db_dir.resolve() / "sync"
    resolved_path = args.resolved_packages.resolve()
    packages = sorted(cache_dir.glob("*.pkg.tar.zst"))
    sync_dbs = sorted(sync_dir.glob("*.db"))

    if len(packages) != args.expected_count:
        raise SystemExit(
            f"cached package count mismatch: expected {args.expected_count}, got {len(packages)}"
        )
    if not resolved_path.is_file():
        raise SystemExit(f"resolution manifest not found: {resolved_path}")
    if not sync_dbs:
        raise SystemExit(f"no Pacman sync databases found under {sync_dir}")
    if shutil.which("bsdtar") is None:
        raise SystemExit("bsdtar is required")

    resolution = load_resolution_manifest(resolved_path, args.expected_count)
    selected_filenames = {str(record["filename"]) for record in resolution}
    cached_filenames = {package.name for package in packages}
    extra_cached = sorted(cached_filenames - selected_filenames)
    missing_cached = sorted(selected_filenames - cached_filenames)
    if extra_cached or missing_cached:
        raise SystemExit(
            "cache/resolution package identity mismatch: "
            + json.dumps(
                {
                    "extra_cached": extra_cached[:50],
                    "missing_cached": missing_cached[:50],
                },
                sort_keys=True,
            )
        )

    # Key by (repository, filename). A filename can legitimately exist in more
    # than one configured repository with different bytes. The original Pacman
    # resolution manifest determines which repository was authoritative.
    authoritative: dict[tuple[str, str], dict[str, str]] = {}
    sync_db_sha256: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="syncdb-verify-") as tmp:
        tmp_root = Path(tmp)
        for db in sync_dbs:
            repository = db.stem
            sync_db_sha256[db.name] = sha256(db)
            repo_root = tmp_root / repository
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
                        f"invalid SHA256SUM in {repository} metadata for {filename}: {expected_sha!r}"
                    )
                key = (repository, filename)
                if key in authoritative:
                    raise SystemExit(
                        f"duplicate package metadata entry in {repository} for filename {filename}"
                    )
                authoritative[key] = {
                    "name": desc.get("NAME", ""),
                    "version": desc.get("VERSION", ""),
                    "sha256": expected_sha,
                }

    verified: list[dict[str, object]] = []
    upstream_sum_lines: list[str] = []
    failures: list[dict[str, object]] = []

    for selected in resolution:
        repository = str(selected["repository"])
        filename = str(selected["filename"])
        metadata = authoritative.get((repository, filename))
        if metadata is None:
            failures.append(
                {
                    "filename": filename,
                    "repository": repository,
                    "error": "selected package absent from saved repository metadata",
                }
            )
            continue

        if metadata["name"] != selected["name"] or metadata["version"] != selected["version"]:
            failures.append(
                {
                    "filename": filename,
                    "repository": repository,
                    "error": "repository metadata identity differs from original resolution manifest",
                    "resolved_name": selected["name"],
                    "resolved_version": selected["version"],
                    "metadata_name": metadata["name"],
                    "metadata_version": metadata["version"],
                }
            )
            continue

        package = cache_dir / filename
        actual = sha256(package)
        expected = metadata["sha256"]
        if actual != expected:
            failures.append(
                {
                    "filename": filename,
                    "repository": repository,
                    "error": "SHA-256 mismatch",
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                }
            )
            continue

        upstream_sum_lines.append(f"{expected}  {filename}")
        verified.append(
            {
                **selected,
                "sha256": actual,
                "saved_repository_metadata_sha256": expected,
                "hashes_identical": True,
            }
        )

    if failures:
        raise SystemExit(
            "upstream package verification failed: "
            + json.dumps({"failures": failures[:50]}, sort_keys=True)
        )
    if len(verified) != args.expected_count:
        raise SystemExit(
            f"verified package count mismatch: expected {args.expected_count}, got {len(verified)}"
        )

    args.upstream_sums.parent.mkdir(parents=True, exist_ok=True)
    args.upstream_sums.write_text("\n".join(upstream_sum_lines) + "\n")

    report = {
        "schema": 2,
        "verification_method": (
            "for each original resolution record, identify the exact selected repository and package "
            "filename; compare sha256(cached bytes) with %SHA256SUM% from that repository's saved "
            "Pacman sync database"
        ),
        "resolution_manifest_sha256": sha256(resolved_path),
        "expected_package_count": args.expected_count,
        "verified_package_count": len(verified),
        "all_cached_packages_match_saved_original_repository_hashes": True,
        "exact_repository_selection_bound": True,
        "sync_database_count": len(sync_dbs),
        "sync_database_sha256": sync_db_sha256,
        "packages": verified,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(
        f"Verified {len(verified)} cached packages against the SHA-256 values from "
        "the exact repositories selected by the original Pacman resolution manifest"
    )


if __name__ == "__main__":
    main()
