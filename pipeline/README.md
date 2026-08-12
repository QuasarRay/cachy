# Hybrid pipeline contract spine

This directory starts the migration to the recommended hybrid architecture without changing the currently working ISO workflows.

## Non-drift rule

`../docs/architecture/cross-candidate-component-contracts.md` is the source of truth for persisted pipeline artifacts. Its locked SHA-256 is:

`a94353b3a477a75c3995d116624f8d2330e526bcc1310e806e63ccbd182e028d`

The Python contract classes normalize punctuation into valid identifiers but preserve a strict one-field-per-contract-line mapping. Tests reject missing or additional persisted fields.

## Phase-1 boundaries

The only pipeline factory interfaces introduced in this slice are:

```text
SoftwareFactory -> RepositoryFactory ----\
                                        -> ImageAssembler
InstallerOverlayFactory -----------------/
SourceLock ------------------------------/
```

They produce/consume only cross-candidate contract types. Factory implementations will migrate existing build logic incrementally; GitHub Actions remains untouched until equivalent Dagger paths exist.

## Local contract tests

```bash
PYTHONPATH=pipeline/src python -m unittest discover -s pipeline/tests -p 'test_*.py' -v
```

## Dagger

The module is pinned to Dagger engine `v0.21.0`. Generate the Python SDK bindings with the Dagger Python SDK module before invoking the façade if `pipeline/sdk/` is absent. The generated SDK is intentionally ignored in this initial slice.
