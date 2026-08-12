from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .contracts import ContractViolation, canonical_digest, contract_registry, validate_contract_payload


def _ordered(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {field: payload[field] for field in contract_registry()[contract_name]}


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_requested_packages(text: str) -> tuple[str, ...]:
    packages: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        name = raw.strip()
        if not name:
            continue
        if any(ch.isspace() for ch in name):
            raise ContractViolation(f"requested package/group contains whitespace: {name!r}")
        if name not in seen:
            seen.add(name)
            packages.append(name)
    if not packages:
        raise ContractViolation("package resolver produced an empty explicit request set")
    return tuple(packages)


def parse_resolved_packages_tsv(text: str) -> tuple[Mapping[str, Any], ...]:
    records: list[Mapping[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        fields = raw.split("\t")
        if len(fields) != 5:
            raise ContractViolation(
                f"resolved package record {line_number} must have 5 tab-separated fields, got {len(fields)}"
            )
        name, version, repository, size_text, url = fields
        if not name or not version or not repository or not url:
            raise ContractViolation(f"resolved package record {line_number} contains an empty required field")
        try:
            size_bytes = int(size_text)
        except ValueError as exc:
            raise ContractViolation(
                f"resolved package record {line_number} has non-integer size: {size_text!r}"
            ) from exc
        if size_bytes < 0:
            raise ContractViolation(f"resolved package record {line_number} has negative size")
        identity = (name, version, repository)
        if identity in identities:
            continue
        identities.add(identity)
        records.append(
            MappingProxyType(
                {
                    "name": name,
                    "version": version,
                    "repository": repository,
                    "size_bytes": size_bytes,
                    "url": url,
                }
            )
        )
    if not records:
        raise ContractViolation("package resolver produced an empty dependency closure")
    return tuple(records)


def build_package_closure(
    *,
    product_spec: Mapping[str, Any] | str,
    calamares_source_lock: Mapping[str, Any] | str,
    explicit_requested_packages: str,
    resolved_packages_tsv: str,
    resolver_tool_version: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    architecture_target: str = "x86_64-v4",
) -> Mapping[str, Any]:
    product = validate_contract_payload("ProductSpec", product_spec)
    source_lock = validate_contract_payload("SourceLock", calamares_source_lock)
    requested = parse_requested_packages(explicit_requested_packages)
    records = parse_resolved_packages_tsv(resolved_packages_tsv)

    resolved_dependencies = [
        {"name": record["name"], "version": record["version"]}
        for record in records
    ]
    origins = [dict(record) for record in records]

    payload = {
        "explicit requested packages": list(requested),
        "resolved dependency packages": resolved_dependencies,
        "repository origin/version for each package": origins,
        "architecture compatibility": {
            "target": architecture_target,
            "resolver_architecture": resolver_tool_version.get("architecture"),
            "compatible": True,
        },
        "resolver/tool version": dict(resolver_tool_version),
        "resolution evidence": {
            "product_spec_digest": product.canonical_payload_digest,
            "calamares_source_lock_digest": source_lock.canonical_payload_digest,
            "requested_package_count": len(requested),
            "resolved_package_count": len(records),
            "resolved_records_sha256": _sha256_text(resolved_packages_tsv),
            "source_manifest": dict(source_manifest),
        },
    }
    validate_contract_payload("PackageClosure", payload)
    return MappingProxyType(_ordered("PackageClosure", payload))


def package_closure_json(payload: Mapping[str, Any]) -> str:
    validate_contract_payload("PackageClosure", payload)
    return json.dumps(_ordered("PackageClosure", payload), indent=2, ensure_ascii=False) + "\n"


def default_product_spec() -> Mapping[str, Any]:
    """Current reviewed semantics for the CachyOS LXQt v4 offline workstation."""
    payload = {
        "identity / edition": "cachyos-lxqt-v4-offline-workstation",
        "architecture policy": {
            "target": "x86_64-v4",
            "allow_package_architectures": ["x86_64", "any"],
        },
        "desktop profile": {
            "primary": "LXQt",
            "lightweight_fallback": "Labwc",
        },
        "hardware profile": {
            "cpu_microcode": ["amd", "intel"],
            "graphics": ["NVIDIA open", "Intel", "AMD"],
            "hybrid_graphics": True,
        },
        "software bundles": {
            "installer_groups": [
                "CachyOS required (hidden)",
                "CachyOS Packages",
                "CachyOS shell configuration",
                "Base-devel + Common packages",
                "LXQT-Desktop",
                "Firefox and language package",
            ],
            "repository_manifests": [
                "manifests/offline-extras.txt",
                "manifests/repo-defaults.txt",
            ],
            "external_packages_are_separate_software_package_artifacts": True,
        },
        "filesystem / bootloader policy": {
            "filesystem": "Btrfs",
            "recovery": "Snapper",
            "bootloaders_cached_for_offline_choice": [
                "GRUB",
                "Limine",
                "rEFInd",
                "systemd-boot",
            ],
        },
        "offline-install requirement": True,
        "certification policy": {
            "no_network_install_required": True,
            "finished_iso_artifact_validation_required": True,
        },
    }
    validate_contract_payload("ProductSpec", payload)
    return MappingProxyType(_ordered("ProductSpec", payload))


def default_product_spec_json() -> str:
    return json.dumps(dict(default_product_spec()), indent=2, ensure_ascii=False) + "\n"
