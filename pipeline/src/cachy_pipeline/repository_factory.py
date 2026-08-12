from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .contracts import (
    ContractViolation,
    canonical_digest,
    contract_registry,
    validate_contract_payload,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _ordered(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {field: payload[field] for field in contract_registry()[contract_name]}


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ContractViolation(f"{label} must be a lowercase sha256:<64 hex> digest")
    return value


def _require_nonempty_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{label} must be a non-empty string")
    return value


def _closure_identities(package_closure: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    records = package_closure["repository origin/version for each package"]
    if not isinstance(records, list) or not records:
        raise ContractViolation("PackageClosure repository-origin records must be a non-empty list")

    identities: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ContractViolation(f"PackageClosure origin record {index} must be an object")
        identity = (
            _require_nonempty_text(record.get("name"), label=f"origin[{index}].name"),
            _require_nonempty_text(record.get("version"), label=f"origin[{index}].version"),
            _require_nonempty_text(record.get("repository"), label=f"origin[{index}].repository"),
        )
        if identity in seen:
            raise ContractViolation(f"PackageClosure contains duplicate package identity: {identity!r}")
        seen.add(identity)
        identities.append(identity)
    return tuple(identities)


def _normalize_package_payloads(
    payloads: Iterable[Mapping[str, Any]],
    *,
    expected_identities: tuple[tuple[str, str, str], ...],
) -> tuple[dict[str, Any], ...]:
    expected = set(expected_identities)
    normalized: list[dict[str, Any]] = []
    seen_identities: set[tuple[str, str, str]] = set()
    seen_filenames: set[str] = set()

    for index, raw in enumerate(payloads):
        record = dict(raw)
        identity = (
            _require_nonempty_text(record.get("name"), label=f"payload[{index}].name"),
            _require_nonempty_text(record.get("version"), label=f"payload[{index}].version"),
            _require_nonempty_text(record.get("repository"), label=f"payload[{index}].repository"),
        )
        if identity not in expected:
            raise ContractViolation(
                "repository payload is not part of PackageClosure: " f"{identity!r}"
            )
        if identity in seen_identities:
            raise ContractViolation(f"duplicate repository payload identity: {identity!r}")
        seen_identities.add(identity)

        filename = _require_nonempty_text(
            record.get("filename"), label=f"payload[{index}].filename"
        )
        if "/" in filename or "\\" in filename or filename in {".", ".."}:
            raise ContractViolation(f"payload filename must be a basename: {filename!r}")
        if filename in seen_filenames:
            raise ContractViolation(f"duplicate repository payload filename: {filename!r}")
        seen_filenames.add(filename)

        size_bytes = record.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ContractViolation(f"payload[{index}].size_bytes must be a non-negative integer")

        normalized.append(
            {
                "name": identity[0],
                "version": identity[1],
                "repository": identity[2],
                "filename": filename,
                "size_bytes": size_bytes,
                "sha256": _require_sha256(record.get("sha256"), label=f"payload[{index}].sha256"),
                "object_ref": _require_nonempty_text(
                    record.get("object_ref"), label=f"payload[{index}].object_ref"
                ),
            }
        )

    missing = expected - seen_identities
    if missing:
        sample = sorted(missing)[:10]
        raise ContractViolation(
            f"RepoSnapshot is missing {len(missing)} PackageClosure payload(s); sample={sample!r}"
        )
    if len(normalized) != len(expected):
        raise ContractViolation(
            "RepoSnapshot payload cardinality does not exactly match PackageClosure"
        )
    return tuple(sorted(normalized, key=lambda item: item["filename"]))


def _normalize_repo_index(value: Mapping[str, Any], *, label: str) -> dict[str, str]:
    record = dict(value)
    return {
        "object_ref": _require_nonempty_text(record.get("object_ref"), label=f"{label}.object_ref"),
        "sha256": _require_sha256(record.get("sha256"), label=f"{label}.sha256"),
    }


def build_repo_snapshot(
    *,
    package_closure: Mapping[str, Any] | str,
    package_payloads: Iterable[Mapping[str, Any]],
    repo_database: Mapping[str, Any],
    files_index: Mapping[str, Any],
    software_packages: Iterable[Mapping[str, Any] | str] = (),
    normalized_metadata_policy: str = "exact-closure-only/v1",
    offline_resolution_evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Build immutable RepoSnapshot metadata from already-verified package bytes.

    This function intentionally does not download packages. The executable Repository
    Factory must hash bytes first and pass those verified records here. The producer
    rejects missing, duplicate and stale payloads so a restored cache directory cannot
    silently broaden the repository beyond PackageClosure.
    """

    closure = validate_contract_payload("PackageClosure", package_closure)
    expected_identities = _closure_identities(closure.payload)
    payload_records = _normalize_package_payloads(
        package_payloads, expected_identities=expected_identities
    )

    database = _normalize_repo_index(repo_database, label="repo_database")
    files = _normalize_repo_index(files_index, label="files_index")
    policy = _require_nonempty_text(normalized_metadata_policy, label="normalized_metadata_policy")

    software_digests: list[str] = []
    for index, software in enumerate(software_packages):
        artifact = validate_contract_payload("SoftwarePackage", software)
        digest = artifact.canonical_payload_digest
        if digest in software_digests:
            raise ContractViolation(f"duplicate SoftwarePackage digest at index {index}: {digest}")
        software_digests.append(digest)
    software_digests.sort()

    evidence = dict(offline_resolution_evidence)
    if evidence.get("network_forbidden") is not True:
        raise ContractViolation("RepoSnapshot offline-resolution evidence must forbid network access")
    if evidence.get("resolved_package_count") != len(expected_identities):
        raise ContractViolation(
            "RepoSnapshot offline-resolution evidence package count does not match PackageClosure"
        )
    if evidence.get("missing_packages") not in ([], ()):
        raise ContractViolation("RepoSnapshot offline resolution reports missing packages")

    sha_manifest = [
        {"filename": record["filename"], "sha256": record["sha256"]}
        for record in payload_records
    ]
    sha_manifest.extend(
        [
            {"filename": "cachyos-lxqt-offline.db", "sha256": database["sha256"]},
            {"filename": "cachyos-lxqt-offline.files", "sha256": files["sha256"]},
        ]
    )

    without_digest = {
        "package payload directory / object references": [dict(record) for record in payload_records],
        "repo database + files index": {
            "database": database,
            "files_index": files,
        },
        "normalized metadata policy": policy,
        "SHA-256 manifest": sha_manifest,
        "PackageClosure reference": {
            "digest": closure.canonical_payload_digest,
            "resolved_package_count": len(expected_identities),
        },
        "SoftwarePackage digests": software_digests,
        "offline-resolution evidence": evidence,
    }
    payload = {
        **without_digest,
        "snapshot digest": canonical_digest(without_digest),
    }
    validate_contract_payload("RepoSnapshot", payload)
    return MappingProxyType(_ordered("RepoSnapshot", payload))
