# Cross-Candidate Component Contracts

## Purpose

These contracts are useful regardless of which candidate architecture is selected. They are intended to keep future Dagger modules reusable rather than coupling them to one GitHub workflow or one ISO edition.

## `ProductSpec`

Describes desired product semantics, not implementation steps.

```text
identity / edition
architecture policy
desktop profile
hardware profile
software bundles
filesystem / bootloader policy
offline-install requirement
certification policy
```

## `SourceLock`

```text
source_name
requested_ref
resolved_commit_or_version
content_digest
retrieval_uri
toolchain_digest
retrieved_at
lock_schema_version
```

Downstream modules accept the resolved lock, never a moving branch.

## `ResourceBudget`

```text
cpu_parallelism
memory_limit_or_target
disk_budget
timeout
retry_class_policy
```

This should be explicit for resource-heavy builders such as Amnezia.

## `SoftwarePackage`

```text
native package payload(s)
package metadata
upstream SourceLock reference
build recipe digest
ResourceBudget used
unit/integration test evidence
SBOM
provenance
payload digest
```

## `PackageClosure`

```text
explicit requested packages
resolved dependency packages
repository origin/version for each package
architecture compatibility
resolver/tool version
resolution evidence
```

## `RepoSnapshot`

```text
package payload directory / object references
repo database + files index
normalized metadata policy
SHA-256 manifest
PackageClosure reference
SoftwarePackage digests
offline-resolution evidence
snapshot digest
```

## `InstallerAdapterCertification`

```text
upstream installer source/package digest
expected sequence/modules
package-owned path inventory
pacstrap/pacman semantic probe results
network-forbidden behavior
supported overlay phases
adapter version
certification digest
```

## `InstallerOverlay`

```text
overlay files/patches
application phase for each operation
preconditions
postconditions
forbidden online behaviors
adapter-certification dependency
overlay digest
```

## `ImageCandidate`

```text
ISO payload
SourceLock digest
RepoSnapshot digest
InstallerOverlay digest
image build toolchain digest
structural verification evidence
candidate digest
```

## `ImageCertification`

```text
no-NIC install result
boot result
desktop/session result
required service/package smoke tests
hardware-profile checks when emulatable
logs/screenshots where useful
certification digest
```

## `FailureEvidence`

```text
stage
attempt
runner identity/class
input artifact digests
last completed checkpoint
exit status/signal
resource telemetry
log digest
failure class
retry recommendation
```

## Contract ownership rule

The module that **produces** an artifact owns its invariants. For example, the Repository Factory should certify repository metadata and offline dependency resolution; GitHub Actions should not contain ad-hoc grep assertions about repository internals.

This rule prevents the stale-assertion problem where implementation layout changes but a distant workflow still encodes old assumptions.
