# CachyOS Hybrid Pipeline — Contract Spine

This directory is the first implementation slice of the recommended hybrid Dagger architecture.

## Non-drift rule

`src/cachy_pipeline/reference/cross-candidate-component-contracts.md` is the authoritative artifact-contract baseline. Its SHA-256 is pinned in `contracts.py`. Any edit fails closed until the baseline is deliberately reviewed and updated.

The implementation does not add domain fields to those contracts. Internal validation/component metadata is an envelope around the contracts, not part of their payloads.

The recommended hybrid architecture mentions `SoftwarePackageSet`, but the cross-candidate contract document does not define a `SoftwarePackageSet` contract. Therefore this implementation models a software set as a collection of `SoftwarePackage` artifacts rather than inventing a new schema.

The recommended-hybrid architecture reference used to derive these boundaries has digest `sha256:32406711947258d1ac045ad17eb9b2396b18b333767656d1086c074dc48b0efd`.

## Implemented boundaries

- source-locker: `ProductSpec -> SourceLock`
- software-factory: `SourceLock + ResourceBudget -> SoftwarePackage`
- package-resolver: `ProductSpec + SourceLock -> PackageClosure`
- repository-factory: `PackageClosure + SoftwarePackage[] -> RepoSnapshot`
- installer-adapter-certifier: `SourceLock -> InstallerAdapterCertification`
- installer-overlay-factory: `ProductSpec + InstallerAdapterCertification -> InstallerOverlay`
- image-factory: `ProductSpec + SourceLock + RepoSnapshot + InstallerOverlay -> ImageCandidate`
- image-certifier: `ProductSpec + ImageCandidate -> ImageCertification`
- failure-classifier: `FailureEvidence -> FailureEvidence`

These are contract boundaries only. Existing build implementation is intentionally not copied into them yet.

## Dagger functions

- `contract-manifest`
- `architecture-manifest`
- `validate-contract`
- `check-contracts`

GitHub Actions should call these functions; it should not duplicate their assertions.
