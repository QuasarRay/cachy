"""Phase-1 factory boundaries from the recommended hybrid architecture.

These protocols define module ownership and dependency direction only. They do not create
new persisted artifact contracts beyond cross-candidate-component-contracts.md.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from .contracts import (
    ImageCandidate,
    InstallerAdapterCertification,
    InstallerOverlay,
    PackageClosure,
    ProductSpec,
    RepoSnapshot,
    ResourceBudget,
    SoftwarePackage,
    SourceLock,
)


class SoftwareFactory(Protocol):
    def build(
        self,
        *,
        product_spec: ProductSpec,
        source_locks: Sequence[SourceLock],
        resource_budget: ResourceBudget,
    ) -> Sequence[SoftwarePackage]: ...


class RepositoryFactory(Protocol):
    def build(
        self,
        *,
        package_closure: PackageClosure,
        software_packages: Sequence[SoftwarePackage],
    ) -> RepoSnapshot: ...


class InstallerOverlayFactory(Protocol):
    def build(
        self,
        *,
        product_spec: ProductSpec,
        adapter_certification: InstallerAdapterCertification,
    ) -> InstallerOverlay: ...


class ImageAssembler(Protocol):
    def build(
        self,
        *,
        source_lock: SourceLock,
        repo_snapshot: RepoSnapshot,
        installer_overlay: InstallerOverlay,
    ) -> ImageCandidate: ...
