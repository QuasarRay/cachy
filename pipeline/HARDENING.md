# Hybrid ISO Pipeline Hardening

This document records concrete failure modes discovered while moving the CachyOS offline ISO from workflow-oriented scripts to artifact-oriented Dagger stages. Items are ordered by their impact on the probability that a build both completes and produces a genuinely offline-installable image.

## P0 — package repository state is still mutable

`SourceLock` freezes Git trees, but `PackageClosure` currently resolves against live Arch/CachyOS repository databases. Two otherwise-green PackageResolver executions can therefore produce different closure digests without any repository code change.

**Required fix:** Repository Factory must materialize every package referenced by `PackageClosure`, verify the downloaded identity/version, hash the actual bytes, build repository metadata only from that exact set, and emit a `RepoSnapshot`. Downstream image construction must consume the snapshot rather than query public mirrors.

## P0 — restored package caches may contain historical payloads

The legacy cache workflow previously used a broad restore prefix and then ran `repo-add` across every `*.pkg.tar.zst` present in the restored directory. Old packages that are no longer in the current closure can therefore become part of the offline repository.

**Required fix:** never build repository metadata directly over a mutable cache directory. Stage a clean snapshot directory containing exactly the verified closure payloads and approved `SoftwarePackage` artifacts. Reject unexpected or missing payloads.

## P0 — image source and installer source were moving refs

The legacy workflows fetched the current Calamares branch and the current CachyOS live-ISO `master` branch during each run.

**Build-run mitigation:** the active validation build pins the already-validated Calamares commit and will pin the already-validated live-ISO commit. Long-term, Image Factory must accept only `SourceLock` artifacts.

## P0 — build-local ISO verification is insufficient

A legacy step named as if it verified the ISO repository actually checked files in the runner cache rather than proving that the produced ISO contained those bytes.

**Required fix:** certification must run from the finished ISO artifact on a fresh runner. It must mount/extract the ISO and root filesystem, validate the embedded repository database and package hashes, verify Calamares offline configuration, and eventually perform a no-NIC installation/boot smoke test.

## P1 — `PackageClosure` does not yet prove package bytes

Names, versions, repositories, sizes and URLs are resolution evidence, not immutable package artifacts. A URL can later serve different state or disappear.

**Required fix:** `RepoSnapshot` owns byte-level SHA-256 manifests, exact package identity coverage, repository DB/files indexes, offline dependency-resolution evidence and a snapshot digest.

## P1 — external software builders are not first-class hybrid stages

Windscribe, sing-box, Xray, VS Code, Tor Browser and Amnezia are currently built by the legacy workflow. They should be independent `SoftwarePackage` producers carrying their `SourceLock`, build-recipe digest, resource budget, tests, SBOM/provenance and payload digest.

## P1 — mutable runner/container toolchains

`archlinux:latest`, live Arch repositories, GitHub runner images, and unrecorded `mkarchiso` versions can change between builds.

**Required fix:** record container image digest and all relevant tool versions in provenance immediately; later pin container images/toolchains where operationally practical.

## P1 — no explicit disk headroom gate

The offline package closure, external packages, archiso work tree and final ISO coexist on the runner. A late disk exhaustion wastes the most expensive part of the build.

**Required fix:** before external builds and before `mkarchiso`, record `df -B1`, estimate required headroom from RepoSnapshot size, and fail early if the budget is insufficient. This belongs to explicit `ResourceBudget`/failure evidence rather than a magic workflow constant.

## P1 — transient network failures lack bounded stage policy

Keyserver access and mirror downloads can fail transiently even when inputs are valid. Retrying whole workflows is expensive and obscures whether failure is environmental or semantic.

**Required fix:** classify network-only operations and give them bounded retry/backoff. Never retry checksum, contract, source-lock, repository-integrity or offline-certification failures as if they were transient.

## P2 — build provenance is fragmented

Useful evidence exists across logs and several manifest files but there is no single candidate manifest joining all immutable inputs and outputs.

**Required fix:** Image Factory should emit one provenance record containing ProductSpec digest, all SourceLock digests, PackageClosure digest, RepoSnapshot digest, SoftwarePackage digests, InstallerOverlay digest, image toolchain versions, ISO SHA-256 and candidate digest.

## P2 — branch/workflow coupling

The legacy package cache was keyed to `github.sha`, forcing expensive re-downloads for workflow-only edits and making a validated package payload difficult to reuse in a controlled build.

**Build-run mitigation:** the active build branch derives its cache key from package-selection inputs rather than the commit SHA. Long-term, the `RepoSnapshot` artifact itself replaces this implicit cache protocol.

## P2 — certification should be a release gate, not a descriptive step

Producing an ISO file is not the final goal. The desired artifact is a bootable image that installs the intended system with networking disabled.

**Required fix:** only an `ImageCandidate` that passes `ImageCertification` should be promoted as a successful final artifact. Structural ISO inspection is the first certification layer; no-NIC installation and boot/session smoke tests are the next layer.
