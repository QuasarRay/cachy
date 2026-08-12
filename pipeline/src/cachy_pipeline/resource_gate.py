from __future__ import annotations

from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .contracts import ContractViolation, contract_registry, validate_contract_payload

_GIB = 1024**3
_OPTIMIZED_V4_REPOSITORIES = {
    "cachyos-v4",
    "cachyos-core-v4",
    "cachyos-extra-v4",
}


def _ordered(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {field: payload[field] for field in contract_registry()[contract_name]}


def validate_host_target_isa_separation(
    *,
    product_spec: Mapping[str, Any] | str,
    host_repositories: Iterable[str],
    target_repositories: Iterable[str],
) -> Mapping[str, Any]:
    """Reject target-optimized repositories in the host execution environment.

    The product may intentionally target x86-64-v4 while CI executes on a
    baseline x86_64 CPU. Package *bytes* for the target can come from v4 repos,
    but tools executed by the runner (libarchive, squashfs-tools, grub, etc.)
    must not be replaced by v4 builds unless a future host capability contract
    explicitly proves that ISA. Keeping host tooling baseline is the fail-safe
    policy and prevents an `Illegal instruction` crash from appearing late in
    image construction.
    """

    product = validate_contract_payload("ProductSpec", product_spec)
    architecture_policy = product.payload["architecture policy"]
    if not isinstance(architecture_policy, Mapping):
        raise ContractViolation("ProductSpec architecture policy must be an object")
    target = architecture_policy.get("target")
    if target != "x86_64-v4":
        raise ContractViolation(
            f"current host/target ISA gate expects x86_64-v4 ProductSpec, got {target!r}"
        )

    host = tuple(dict.fromkeys(str(repo).strip() for repo in host_repositories if str(repo).strip()))
    target_repos = tuple(
        dict.fromkeys(str(repo).strip() for repo in target_repositories if str(repo).strip())
    )
    if not host:
        raise ContractViolation("host repository inventory must not be empty")
    if not target_repos:
        raise ContractViolation("target repository inventory must not be empty")

    unsafe_host = sorted(set(host) & _OPTIMIZED_V4_REPOSITORIES)
    if unsafe_host:
        raise ContractViolation(
            "x86-64-v4 repositories must not supply host-executed CI tools; "
            f"unsafe host repositories={unsafe_host!r}"
        )
    if not (set(target_repos) & _OPTIMIZED_V4_REPOSITORIES):
        raise ContractViolation(
            "x86-64-v4 target profile must include at least one CachyOS v4 repository"
        )

    return MappingProxyType(
        {
            "target_architecture": target,
            "host_repository_policy": "baseline-x86_64-only",
            "host_repositories": list(host),
            "target_repositories": list(target_repos),
            "separated": True,
        }
    )


def default_iso_resource_budget() -> Mapping[str, Any]:
    """Emit the explicit budget used by the expensive offline ISO stages."""

    payload = {
        "cpu_parallelism": 2,
        "memory_limit_or_target": {
            "minimum_bytes": 4 * _GIB,
            "target_bytes": 8 * _GIB,
            "policy": "bounded-parallel-build",
        },
        "disk_budget": {
            "minimum_free_bytes_before_image_build": 20 * _GIB,
            "formula": "2 * RepoSnapshot_bytes + 8GiB",
            "fail_before_expensive_stage": True,
        },
        "timeout": {
            "external_package_build_seconds": 90 * 60,
            "image_build_seconds": 240 * 60,
            "certification_seconds": 90 * 60,
        },
        "retry_class_policy": {
            "transient_network": {
                "max_attempts": 3,
                "bounded_exponential_backoff": True,
            },
            "contract_or_integrity_failure": {"max_attempts": 1},
            "resource_gate_failure": {"max_attempts": 1},
            "offline_certification_failure": {"max_attempts": 1},
        },
    }
    validate_contract_payload("ResourceBudget", payload)
    return MappingProxyType(_ordered("ResourceBudget", payload))
