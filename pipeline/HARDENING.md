# Hybrid ISO Pipeline Hardening

This document records concrete failure modes discovered while moving the CachyOS offline ISO from workflow-oriented scripts to artifact-oriented Dagger stages. Items are ordered by their impact on the probability that a build both completes and produces a genuinely offline-installable image.

## P0 — package repository state is still mutable

`SourceLock` freezes Git trees, but `PackageClosure` currently resolves against live Arch/CachyOS repository databases. Two otherwise-green PackageResolver executions can therefore produce different closure digests without any repository code change.

**Required fix:** Repository Factory must materialize every package referenced by `PackageClosure`, verify the downloaded identity/version, hash the actual bytes, build repository metadata only from that exact set, and emit a `RepoSnapshot`. Downstream image construction must consume the snapshot rather than query public mirrors.

**Hardening branch:** `repository_factory.py` now defines fail-closed `RepoSnapshot` metadata construction that rejects stale, duplicate and missing closure payloads, binds actual package SHA-256s, repository indexes, `SoftwarePackage` digests and zero-network resolution evidence into the snapshot digest.

## P0 — restored package caches may contain historical payloads

The legacy cache workflow previously used a broad restore prefix and then ran `repo-add` across every `*.pkg.tar.zst` present in the restored directory. Old packages that are no longer in the current closure can therefore become part of the offline repository.

**Required fix:** never build repository metadata directly over a mutable cache directory. Stage a clean snapshot directory containing exactly the verified closure payloads and approved `SoftwarePackage` artifacts. Reject unexpected or missing payloads.

**Build-run mitigation:** the active build uses a content-derived exact cache key with no broad restore prefix and validates `SHA256SUMS` before consuming the cache.

## P0 — target ISA leaked into host-executed build tools

The first locked build enabled CachyOS x86-64-v4 repositories in the build container itself. That upgraded host-executed tools such as `libarchive` to v4 binaries. GitHub's hosted CPU did not satisfy that ISA, so Xray extraction died with `Illegal instruction` even though the final product is intentionally x86-64-v4.

**Required fix:** target architecture and host execution architecture are distinct contracts. The runner/tool container must remain baseline x86_64 unless host capability is explicitly certified. Only target package bytes and the image profile may use CachyOS v4 repositories.

**Hardening branch:** `resource_gate.py` now rejects v4 repositories in the host repository inventory while requiring v4 repositories in the x86-64-v4 target inventory. `ResourceBudget` is also explicit and tested.

## P0 — image and installer sources contained moving refs

The legacy workflows fetched the current Calamares branch and the current CachyOS live-ISO `master` branch during each run. A second moving-source path was found inside `prepare-offline-profile.py`: it fetched the pacstrap wrapper and desktop chooser from `raw.githubusercontent.com/.../cachyos` while constructing the supposedly locked overlay.

**Build-run mitigation:** the active validation build pins the already-validated Calamares and live-ISO commits. The live-ISO helper that fetched a mirrorlist from moving `CachyOS-PKGBUILDS/master` is patched to consume the locally installed versioned mirrorlist instead.

**Hardening branch:** `prepare-offline-profile.py` now requires the locked Calamares tree as an input and reads both patched files from that tree. A hermetic regression test executes the builder against a synthetic locked tree and asserts that no network-fetch API remains.

Long-term, Image Factory and Installer Overlay must accept only `SourceLock`/adapter artifacts.

## P0 — build-local ISO verification was insufficient

A legacy step named as if it verified the ISO repository actually checked files in the runner cache rather than proving that the produced ISO contained those bytes.

**Required fix:** certification must run from the finished ISO artifact on a fresh runner. It must extract the ISO and root filesystem, validate the embedded repository database and package hashes, verify Calamares offline configuration, and eventually perform a no-NIC installation/boot smoke test.

**Confirmed historical defect:** the hardened fresh-runner validator successfully extracted the previous 3.0 GiB ISO and proved that `/var/cache/pacman/pkg` did not contain the expected offline repository database. The old green build was therefore a real false green, not merely a validator incompatibility.

## P0 — independent validator depended on loop mounting

The first real independent-validator run downloaded a finished 3.0 GiB ISO successfully but exited immediately after entering `verify-offline-iso.sh`, before any repository/Calamares evidence was emitted. The validator's first artifact operation was a privileged loop mount, coupling certification to hosted-runner kernel/device policy.

**Hardening branch:** the validator now extracts `arch/x86_64/airootfs.sfs` from ISO9660 with `bsdtar` in userspace and then applies `unsquashfs` to the extracted image. A regression test forbids reintroducing loop-mount/losetup dependence. Cleanup is also fail-safe so SquashFS-restored permissions cannot replace the real validation error with a trap failure.

## P1 — `PackageClosure` does not yet prove package bytes

Names, versions, repositories, sizes and URLs are resolution evidence, not immutable package artifacts. A URL can later serve different state or disappear.

**Required fix:** `RepoSnapshot` owns byte-level SHA-256 manifests, exact package identity coverage, repository DB/files indexes, offline dependency-resolution evidence and a snapshot digest.

## P1 — external software builders are not first-class hybrid stages

Windscribe, sing-box, Xray, VS Code and Tor Browser are currently selected through moving release channels inside the legacy builder; Amnezia alone is pinned to a specific source release. A build can therefore change external payloads even when ProductSpec and Git sources do not.

**Required fix:** each external input becomes a `SourceLock` first, then an independent `SoftwarePackage` producer carrying that lock, build-recipe digest, `ResourceBudget`, tests, SBOM/provenance and payload digest. `SourceLock` has been generalized on the hardening branch so `resolved_commit_or_version` can represent an immutable release version while Git producers retain stricter object-ID validation.

## P1 — package builders published incidental split outputs

Arch `makepkg` produced the intended `xray-offline` package plus `xray-offline-debug`. The legacy builder copied `*.pkg.tar.zst` wholesale, so an incidental split package crossed the artifact boundary and caused a seven-file output where the product specification requires six external package identities.

**Required fix:** Software Package Builder output is selected by parsed `.PKGINFO` identity, never wildcard filenames or file count. Split debug artifacts can be retained as diagnostics, but they are not promoted into `RepoSnapshot` unless explicitly requested by ProductSpec. The build-run branch now normalizes package outputs to the exact six intended `pkgname` values and emits a SHA-256/package manifest checkpoint.

## P1 — mutable runner/container toolchains

`archlinux:latest`, live Arch repositories, GitHub runner images, and unrecorded `mkarchiso` versions can change between builds.

**Required fix:** record container image digest and all relevant tool versions in provenance immediately; later pin container images/toolchains where operationally practical.

## P1 — no explicit disk headroom gate

The offline package closure, external packages, archiso work tree and final ISO coexist on the runner. A late disk exhaustion wastes the most expensive part of the build.

**Build-run mitigation:** the active locked build records cache size/free space and requires free bytes to exceed twice the repository payload plus 8 GiB before invoking `mkarchiso`.

**Hardening branch:** `ResourceBudget` now carries explicit CPU, memory, disk, timeout and retry-class policy rather than relying only on workflow-local constants.

## P1 — transient network failures lack bounded stage policy

Keyserver access and mirror/release downloads can fail transiently even when inputs are valid. Retrying whole workflows is expensive and obscures whether failure is environmental or semantic.

**Required fix:** classify network-only operations and give them bounded retry/backoff. Never retry checksum, contract, source-lock, repository-integrity or offline-certification failures as if they were transient.

## P1 — successful expensive stages were not reusable checkpoints

The first locked run successfully built Amnezia before a later external-package failure. A monolithic retry would have rebuilt it unnecessarily. The same problem applies to the 5+ GiB repository payload and, eventually, completed SoftwarePackage sets.

**Required fix:** every expensive immutable boundary should emit a content-verified artifact that a downstream retry can consume independently. Amnezia and the normalized external-package set are now treated as checkpoints in the build-run branch; the long-term equivalents are `SoftwarePackage` and `RepoSnapshot` artifacts.

## P2 — build provenance is fragmented

Useful evidence exists across logs and several manifest files but there is no single candidate manifest joining all immutable inputs and outputs.

**Build-run mitigation:** the locked build records its repository commit, Calamares commit, live-ISO commit, exact package cache key, toolchain evidence and final ISO SHA-256 as artifacts.

**Required fix:** Image Factory should emit one provenance record containing ProductSpec digest, all SourceLock digests, PackageClosure digest, RepoSnapshot digest, SoftwarePackage digests, InstallerOverlay digest, image toolchain versions, ISO SHA-256 and candidate digest.

## P2 — branch/workflow coupling

The legacy package cache was keyed to `github.sha`, forcing expensive re-downloads for workflow-only edits and making a validated package payload difficult to reuse in a controlled build.

**Build-run mitigation:** the active build branch derives its cache key from package-selection inputs rather than the commit SHA. Long-term, the `RepoSnapshot` artifact itself replaces this implicit cache protocol.

## P2 — certification should be a release gate, not a descriptive step

Producing an ISO file is not the final goal. The desired artifact is a bootable image that installs the intended system with networking disabled.

**Required fix:** only an `ImageCandidate` that passes `ImageCertification` should be promoted as a successful final artifact. Structural ISO inspection is the first certification layer; no-NIC installation and boot/session smoke tests are the next layer.
