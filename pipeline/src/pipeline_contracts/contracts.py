"""Canonical cross-candidate pipeline artifact contracts.

This module intentionally mirrors docs/architecture/cross-candidate-component-contracts.md.
Do not add, remove, split, merge, or rename persisted fields here without first changing
that architecture contract explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from typing import Any, ClassVar, Self


CONTRACT_SOURCE_SHA256 = (
    "a94353b3a477a75c3995d116624f8d2330e526bcc1310e806e63ccbd182e028d"
)

# Each Python identifier maps one-to-one to one line of the architecture contract.
# Punctuation/slashes/spaces are normalized only so the line is a valid identifier.
CANONICAL_CONTRACT_FIELDS: dict[str, tuple[str, ...]] = {
    "ProductSpec": (
        "identity_edition",
        "architecture_policy",
        "desktop_profile",
        "hardware_profile",
        "software_bundles",
        "filesystem_bootloader_policy",
        "offline_install_requirement",
        "certification_policy",
    ),
    "SourceLock": (
        "source_name",
        "requested_ref",
        "resolved_commit_or_version",
        "content_digest",
        "retrieval_uri",
        "toolchain_digest",
        "retrieved_at",
        "lock_schema_version",
    ),
    "ResourceBudget": (
        "cpu_parallelism",
        "memory_limit_or_target",
        "disk_budget",
        "timeout",
        "retry_class_policy",
    ),
    "SoftwarePackage": (
        "native_package_payloads",
        "package_metadata",
        "upstream_source_lock_reference",
        "build_recipe_digest",
        "resource_budget_used",
        "unit_integration_test_evidence",
        "sbom",
        "provenance",
        "payload_digest",
    ),
    "PackageClosure": (
        "explicit_requested_packages",
        "resolved_dependency_packages",
        "repository_origin_version_for_each_package",
        "architecture_compatibility",
        "resolver_tool_version",
        "resolution_evidence",
    ),
    "RepoSnapshot": (
        "package_payload_directory_object_references",
        "repo_database_files_index",
        "normalized_metadata_policy",
        "sha256_manifest",
        "package_closure_reference",
        "software_package_digests",
        "offline_resolution_evidence",
        "snapshot_digest",
    ),
    "InstallerAdapterCertification": (
        "upstream_installer_source_package_digest",
        "expected_sequence_modules",
        "package_owned_path_inventory",
        "pacstrap_pacman_semantic_probe_results",
        "network_forbidden_behavior",
        "supported_overlay_phases",
        "adapter_version",
        "certification_digest",
    ),
    "InstallerOverlay": (
        "overlay_files_patches",
        "application_phase_for_each_operation",
        "preconditions",
        "postconditions",
        "forbidden_online_behaviors",
        "adapter_certification_dependency",
        "overlay_digest",
    ),
    "ImageCandidate": (
        "iso_payload",
        "source_lock_digest",
        "repo_snapshot_digest",
        "installer_overlay_digest",
        "image_build_toolchain_digest",
        "structural_verification_evidence",
        "candidate_digest",
    ),
    "ImageCertification": (
        "no_nic_install_result",
        "boot_result",
        "desktop_session_result",
        "required_service_package_smoke_tests",
        "hardware_profile_checks_when_emulatable",
        "logs_screenshots_where_useful",
        "certification_digest",
    ),
    "FailureEvidence": (
        "stage",
        "attempt",
        "runner_identity_class",
        "input_artifact_digests",
        "last_completed_checkpoint",
        "exit_status_signal",
        "resource_telemetry",
        "log_digest",
        "failure_class",
        "retry_recommendation",
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class ContractModel:
    """Strict serialization behavior shared by all persisted contracts.

    This base class adds behavior, not persisted fields.
    """

    CONTRACT_NAME: ClassVar[str]

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Self:
        expected = set(cls.field_names())
        actual = set(payload)
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing or unknown:
            raise ValueError(
                f"{cls.__name__} contract mismatch: missing={missing}, unknown={unknown}"
            )
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        # Contract values must be persistable evidence, not runtime objects.
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return value

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def metadata_digest(self) -> str:
        """Digest the entire contract document without redefining artifact digest fields."""
        return f"sha256:{sha256(self.canonical_json().encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductSpec(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "ProductSpec"
    identity_edition: Any
    architecture_policy: Any
    desktop_profile: Any
    hardware_profile: Any
    software_bundles: Any
    filesystem_bootloader_policy: Any
    offline_install_requirement: Any
    certification_policy: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceLock(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "SourceLock"
    source_name: Any
    requested_ref: Any
    resolved_commit_or_version: Any
    content_digest: Any
    retrieval_uri: Any
    toolchain_digest: Any
    retrieved_at: Any
    lock_schema_version: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceBudget(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "ResourceBudget"
    cpu_parallelism: Any
    memory_limit_or_target: Any
    disk_budget: Any
    timeout: Any
    retry_class_policy: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class SoftwarePackage(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "SoftwarePackage"
    native_package_payloads: Any
    package_metadata: Any
    upstream_source_lock_reference: Any
    build_recipe_digest: Any
    resource_budget_used: Any
    unit_integration_test_evidence: Any
    sbom: Any
    provenance: Any
    payload_digest: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class PackageClosure(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "PackageClosure"
    explicit_requested_packages: Any
    resolved_dependency_packages: Any
    repository_origin_version_for_each_package: Any
    architecture_compatibility: Any
    resolver_tool_version: Any
    resolution_evidence: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoSnapshot(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "RepoSnapshot"
    package_payload_directory_object_references: Any
    repo_database_files_index: Any
    normalized_metadata_policy: Any
    sha256_manifest: Any
    package_closure_reference: Any
    software_package_digests: Any
    offline_resolution_evidence: Any
    snapshot_digest: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class InstallerAdapterCertification(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "InstallerAdapterCertification"
    upstream_installer_source_package_digest: Any
    expected_sequence_modules: Any
    package_owned_path_inventory: Any
    pacstrap_pacman_semantic_probe_results: Any
    network_forbidden_behavior: Any
    supported_overlay_phases: Any
    adapter_version: Any
    certification_digest: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class InstallerOverlay(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "InstallerOverlay"
    overlay_files_patches: Any
    application_phase_for_each_operation: Any
    preconditions: Any
    postconditions: Any
    forbidden_online_behaviors: Any
    adapter_certification_dependency: Any
    overlay_digest: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class ImageCandidate(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "ImageCandidate"
    iso_payload: Any
    source_lock_digest: Any
    repo_snapshot_digest: Any
    installer_overlay_digest: Any
    image_build_toolchain_digest: Any
    structural_verification_evidence: Any
    candidate_digest: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class ImageCertification(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "ImageCertification"
    no_nic_install_result: Any
    boot_result: Any
    desktop_session_result: Any
    required_service_package_smoke_tests: Any
    hardware_profile_checks_when_emulatable: Any
    logs_screenshots_where_useful: Any
    certification_digest: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class FailureEvidence(ContractModel):
    CONTRACT_NAME: ClassVar[str] = "FailureEvidence"
    stage: Any
    attempt: Any
    runner_identity_class: Any
    input_artifact_digests: Any
    last_completed_checkpoint: Any
    exit_status_signal: Any
    resource_telemetry: Any
    log_digest: Any
    failure_class: Any
    retry_recommendation: Any


CONTRACT_TYPES: dict[str, type[ContractModel]] = {
    contract_type.__name__: contract_type
    for contract_type in (
        ProductSpec,
        SourceLock,
        ResourceBudget,
        SoftwarePackage,
        PackageClosure,
        RepoSnapshot,
        InstallerAdapterCertification,
        InstallerOverlay,
        ImageCandidate,
        ImageCertification,
        FailureEvidence,
    )
}
