from __future__ import annotations

import pytest

from cachy_pipeline.contracts import ContractViolation, canonical_digest, contract_registry
from cachy_pipeline.package_resolver import build_package_closure, default_product_spec
from cachy_pipeline.repository_factory import build_repo_snapshot


def _source_lock() -> dict[str, object]:
    return {
        "source_name": "cachyos-calamares",
        "requested_ref": "cachyos",
        "resolved_commit_or_version": "f" * 40,
        "content_digest": "sha256:" + "1" * 64,
        "retrieval_uri": "https://github.com/CachyOS/cachyos-calamares.git",
        "toolchain_digest": "sha256:" + "2" * 64,
        "retrieved_at": "2026-08-12T00:00:00Z",
        "lock_schema_version": "1",
    }


def _closure():
    return build_package_closure(
        product_spec=default_product_spec(),
        calamares_source_lock=_source_lock(),
        explicit_requested_packages="alpha\nbeta\n",
        resolved_packages_tsv=(
            "alpha\t1.0-1\tcachyos-v4\t10\thttps://mirror.invalid/alpha.pkg.tar.zst\n"
            "beta\t2.0-1\textra\t20\thttps://mirror.invalid/beta.pkg.tar.zst\n"
        ),
        resolver_tool_version={
            "architecture": "x86_64",
            "repository_policy": "cachyos-v4",
            "pacman": "Pacman v7",
        },
        source_manifest={"network_fetches": 0},
    )


def _payloads():
    return [
        {
            "name": "alpha",
            "version": "1.0-1",
            "repository": "cachyos-v4",
            "filename": "alpha-1.0-1-x86_64.pkg.tar.zst",
            "size_bytes": 10,
            "sha256": "sha256:" + "a" * 64,
            "object_ref": "dagger://repo/alpha",
        },
        {
            "name": "beta",
            "version": "2.0-1",
            "repository": "extra",
            "filename": "beta-2.0-1-x86_64.pkg.tar.zst",
            "size_bytes": 20,
            "sha256": "sha256:" + "b" * 64,
            "object_ref": "dagger://repo/beta",
        },
    ]


def _snapshot(**overrides):
    arguments = {
        "package_closure": _closure(),
        "package_payloads": _payloads(),
        "repo_database": {
            "object_ref": "dagger://repo/cachyos-lxqt-offline.db",
            "sha256": "sha256:" + "c" * 64,
        },
        "files_index": {
            "object_ref": "dagger://repo/cachyos-lxqt-offline.files",
            "sha256": "sha256:" + "d" * 64,
        },
        "offline_resolution_evidence": {
            "network_forbidden": True,
            "resolved_package_count": 2,
            "missing_packages": [],
            "command": "pacman -S --sysroot isolated-root",
        },
    }
    arguments.update(overrides)
    return build_repo_snapshot(**arguments)


def test_repo_snapshot_uses_exact_contract_order_and_self_digest():
    snapshot = _snapshot()
    assert tuple(snapshot) == contract_registry()["RepoSnapshot"]

    without_digest = {
        field: snapshot[field]
        for field in contract_registry()["RepoSnapshot"]
        if field != "snapshot digest"
    }
    assert snapshot["snapshot digest"] == canonical_digest(without_digest)


def test_repo_snapshot_manifest_covers_payloads_and_repository_indexes():
    snapshot = _snapshot()
    manifest = snapshot["SHA-256 manifest"]
    assert [entry["filename"] for entry in manifest] == [
        "alpha-1.0-1-x86_64.pkg.tar.zst",
        "beta-2.0-1-x86_64.pkg.tar.zst",
        "cachyos-lxqt-offline.db",
        "cachyos-lxqt-offline.files",
    ]


def test_repo_snapshot_rejects_stale_payload_not_in_closure():
    payloads = _payloads()
    payloads.append(
        {
            "name": "stale",
            "version": "9-1",
            "repository": "extra",
            "filename": "stale-9-1-x86_64.pkg.tar.zst",
            "size_bytes": 1,
            "sha256": "sha256:" + "e" * 64,
            "object_ref": "dagger://repo/stale",
        }
    )
    with pytest.raises(ContractViolation, match="not part of PackageClosure"):
        _snapshot(package_payloads=payloads)


def test_repo_snapshot_rejects_missing_closure_payload():
    with pytest.raises(ContractViolation, match="missing 1 PackageClosure payload"):
        _snapshot(package_payloads=_payloads()[:1])


def test_repo_snapshot_requires_network_forbidden_offline_evidence():
    with pytest.raises(ContractViolation, match="must forbid network access"):
        _snapshot(
            offline_resolution_evidence={
                "network_forbidden": False,
                "resolved_package_count": 2,
                "missing_packages": [],
            }
        )


def test_repo_snapshot_digest_changes_when_verified_package_bytes_change():
    first = _snapshot()
    changed_payloads = _payloads()
    changed_payloads[0]["sha256"] = "sha256:" + "f" * 64
    second = _snapshot(package_payloads=changed_payloads)
    assert first["snapshot digest"] != second["snapshot digest"]
