from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .contracts import ContractViolation, contract_registry


@dataclass(frozen=True, slots=True)
class ComponentBoundary:
    """Pipeline component metadata; domain artifact fields remain in contracts.py."""

    name: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    owns_invariants_of: tuple[str, ...]


# The recommended hybrid graph expressed only in cross-candidate contracts.
# FailureEvidence is out-of-band evidence available to every executable stage.
_BOUNDARIES = (
    ComponentBoundary(
        name="source-locker",
        consumes=("ProductSpec",),
        produces=("SourceLock",),
        owns_invariants_of=("SourceLock",),
    ),
    ComponentBoundary(
        name="software-factory",
        consumes=("SourceLock", "ResourceBudget"),
        produces=("SoftwarePackage",),
        owns_invariants_of=("SoftwarePackage",),
    ),
    ComponentBoundary(
        name="package-resolver",
        consumes=("ProductSpec", "SourceLock"),
        produces=("PackageClosure",),
        owns_invariants_of=("PackageClosure",),
    ),
    ComponentBoundary(
        name="repository-factory",
        consumes=("PackageClosure", "SoftwarePackage"),
        produces=("RepoSnapshot",),
        owns_invariants_of=("RepoSnapshot",),
    ),
    ComponentBoundary(
        name="installer-adapter-certifier",
        consumes=("SourceLock",),
        produces=("InstallerAdapterCertification",),
        owns_invariants_of=("InstallerAdapterCertification",),
    ),
    ComponentBoundary(
        name="installer-overlay-factory",
        consumes=("ProductSpec", "InstallerAdapterCertification"),
        produces=("InstallerOverlay",),
        owns_invariants_of=("InstallerOverlay",),
    ),
    ComponentBoundary(
        name="image-factory",
        consumes=("ProductSpec", "SourceLock", "RepoSnapshot", "InstallerOverlay"),
        produces=("ImageCandidate",),
        owns_invariants_of=("ImageCandidate",),
    ),
    ComponentBoundary(
        name="image-certifier",
        consumes=("ProductSpec", "ImageCandidate"),
        produces=("ImageCertification",),
        owns_invariants_of=("ImageCertification",),
    ),
    ComponentBoundary(
        name="failure-classifier",
        consumes=("FailureEvidence",),
        produces=("FailureEvidence",),
        owns_invariants_of=("FailureEvidence",),
    ),
)


def component_boundaries() -> tuple[ComponentBoundary, ...]:
    validate_component_boundaries()
    return _BOUNDARIES


def validate_component_boundaries() -> None:
    contracts = set(contract_registry())
    names: set[str] = set()
    for boundary in _BOUNDARIES:
        if boundary.name in names:
            raise ContractViolation(f"duplicate component boundary name: {boundary.name}")
        names.add(boundary.name)

        referenced = set(boundary.consumes + boundary.produces + boundary.owns_invariants_of)
        undefined = referenced - contracts
        if undefined:
            raise ContractViolation(
                f"{boundary.name} references undefined cross-candidate contracts: {sorted(undefined)}"
            )

        if set(boundary.owns_invariants_of) != set(boundary.produces):
            raise ContractViolation(
                f"{boundary.name} must own exactly the invariants of the artifacts it produces"
            )


def architecture_manifest() -> Mapping[str, Mapping[str, tuple[str, ...]]]:
    return MappingProxyType(
        {
            boundary.name: MappingProxyType(
                {
                    "consumes": boundary.consumes,
                    "produces": boundary.produces,
                    "owns_invariants_of": boundary.owns_invariants_of,
                }
            )
            for boundary in component_boundaries()
        }
    )
