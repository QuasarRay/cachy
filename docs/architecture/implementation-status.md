# Recommended hybrid pipeline — implementation status

## Current slice

This change establishes the contract spine only. It does **not** replace the existing ISO or package-cache workflows yet.

Architecture reference:

- recommended hybrid architecture SHA-256: `32406711947258d1ac045ad17eb9b2396b18b333767656d1086c074dc48b0efd`;
- cross-candidate component contract SHA-256: `a94353b3a477a75c3995d116624f8d2330e526bcc1310e806e63ccbd182e028d`.

Only the cross-candidate component contract is copied into the repository as an authoritative persisted-interface source. The architecture narrative is referenced by digest rather than duplicated, so an accidental textual variation cannot masquerade as the selected architecture.

Implemented:

- byte-locked copy of the cross-candidate component contract;
- strict Python models for every cross-candidate persisted artifact contract;
- exact-shape tests that reject missing or additional persisted fields;
- canonical JSON/digest behavior for contract documents;
- phase-1 factory protocols for Software Factory, Repository Factory, Installer Overlay Factory, and Image Assembler;
- a thin Dagger façade that exposes the contract manifest and contract test execution.

Not implemented yet:

- concrete Software Factory migration;
- PackageClosure/RepoSnapshot assembly in Dagger;
- installer adapter certification and overlay generation;
- ISO assembly in Dagger;
- durable OCI/CAS checkpoints;
- no-NIC VM certification;
- FailureEvidence classification/recovery;
- thin replacement GitHub Actions workflows.

## Migration rule

Existing GitHub Actions build semantics remain authoritative only as transitional behavior. A YAML step is removed only after its behavior is owned by a Dagger factory that consumes/produces the locked component contracts and has tests for its invariants.

No new package lists, pacman semantics, Calamares edits, or ISO assembly rules should be added to GitHub Actions during the migration.
