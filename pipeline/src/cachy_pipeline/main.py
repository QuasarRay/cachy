from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

import dagger
from dagger import dag, function, object_type

from .components import architecture_manifest, validate_component_boundaries
from .contracts import ContractViolation, contract_manifest_json, validate_contract_payload
from .package_resolver import (
    build_package_closure,
    default_product_spec,
    default_product_spec_json,
    package_closure_json,
)
from .source_locker import build_git_source_lock, source_lock_json

_SOURCE_LOCKER_TOOLCHAIN = (
    "cachy-source-locker-v1|dagger-engine-v0.21.8|"
    "git.ref.commit|git.commit.tree(discard_git_dir=true).digest"
)
_CALAMARES_URI = "https://github.com/CachyOS/cachyos-calamares.git"
_CALAMARES_REF = "cachyos"
_ARCH_IMAGE = "archlinux:latest"


def _source_locker_toolchain_digest() -> str:
    return "sha256:" + hashlib.sha256(_SOURCE_LOCKER_TOOLCHAIN.encode("utf-8")).hexdigest()


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


async def _resolve_git_source_lock(
    source_name: str,
    retrieval_uri: str,
    requested_ref: str,
) -> Mapping[str, Any]:
    repository = dag.git(retrieval_uri)
    requested = repository.ref(requested_ref)
    resolved_commit = await requested.commit()

    immutable = repository.commit(resolved_commit)
    confirmed_commit = await immutable.commit()
    if confirmed_commit != resolved_commit:
        raise RuntimeError(
            "Git source changed identity after immutable resolution: "
            f"expected {resolved_commit}, got {confirmed_commit}"
        )

    content_digest = await immutable.tree(discard_git_dir=True).digest()
    return build_git_source_lock(
        source_name=source_name,
        requested_ref=requested_ref,
        resolved_commit_or_version=resolved_commit,
        content_digest=content_digest,
        retrieval_uri=retrieval_uri,
        toolchain_digest=_source_locker_toolchain_digest(),
        retrieved_at=_utc_now_rfc3339(),
    )


def _parse_checksum_file(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        digest, separator, filename = raw.partition("  ")
        if not separator or not filename:
            raise ContractViolation(f"malformed repository DB checksum line: {raw!r}")
        result[filename.strip()] = "sha256:" + digest.strip()
    if not result:
        raise ContractViolation("resolver captured no synchronized repository database checksums")
    return result


@object_type
class CachyPipeline:
    """Contract-first entrypoint for the hybrid CachyOS build pipeline."""

    @function
    def contract_manifest(self) -> str:
        """Return the exact field set of every cross-candidate artifact contract."""
        return contract_manifest_json()

    @function
    def architecture_manifest(self) -> str:
        """Return producer/consumer boundaries constrained to defined contracts."""
        validate_component_boundaries()
        serializable = {
            component: {key: list(value) for key, value in metadata.items()}
            for component, metadata in architecture_manifest().items()
        }
        return json.dumps(serializable, indent=2, sort_keys=True) + "\n"

    @function
    def validate_contract(self, contract_name: str, payload: str) -> str:
        """Validate a payload and return its canonical content digest."""
        return validate_contract_payload(contract_name, payload).canonical_payload_digest

    @function
    def product_spec(self) -> str:
        """Return the current CachyOS LXQt v4 offline-workstation ProductSpec."""
        return default_product_spec_json()

    @function
    async def lock_git_source(
        self,
        source_name: str,
        retrieval_uri: str,
        requested_ref: str,
    ) -> str:
        """Resolve a Git source once and emit an immutable SourceLock JSON artifact."""
        lock = await _resolve_git_source_lock(source_name, retrieval_uri, requested_ref)
        return source_lock_json(lock)

    async def _package_closure_from_lock(
        self,
        source: dagger.Directory,
        product_spec: Mapping[str, Any] | str,
        calamares_source_lock: Mapping[str, Any] | str,
    ) -> Mapping[str, Any]:
        product = validate_contract_payload("ProductSpec", product_spec)
        lock = validate_contract_payload("SourceLock", calamares_source_lock)
        locked = lock.payload
        if locked["source_name"] != "cachyos-calamares":
            raise ContractViolation(
                "package-resolver requires a SourceLock for cachyos-calamares; "
                f"got {locked['source_name']!r}"
            )

        immutable = dag.git(locked["retrieval_uri"]).commit(
            locked["resolved_commit_or_version"]
        )
        confirmed_commit = await immutable.commit()
        if confirmed_commit != locked["resolved_commit_or_version"]:
            raise ContractViolation(
                "locked Calamares commit could not be reproduced exactly: "
                f"expected {locked['resolved_commit_or_version']}, got {confirmed_commit}"
            )
        calamares_tree = immutable.tree(discard_git_dir=True)
        actual_tree_digest = await calamares_tree.digest()
        if actual_tree_digest != locked["content_digest"]:
            raise ContractViolation(
                "locked Calamares tree digest mismatch: "
                f"expected {locked['content_digest']}, got {actual_tree_digest}"
            )

        resolver_script = r'''
set -euo pipefail
pacman -Syu --noconfirm --needed python python-yaml ca-certificates gnupg
pacman-key --init
pacman-key --populate archlinux
pacman-key --recv-keys F3B607488DB35A47 --keyserver keyserver.ubuntu.com
pacman-key --lsign-key F3B607488DB35A47
pacman -U --noconfirm \
  https://mirror.cachyos.org/repo/x86_64/cachyos/cachyos-keyring-20240331-1-any.pkg.tar.zst \
  https://mirror.cachyos.org/repo/x86_64/cachyos/cachyos-mirrorlist-27-1-any.pkg.tar.zst \
  https://mirror.cachyos.org/repo/x86_64/cachyos/cachyos-v3-mirrorlist-27-1-any.pkg.tar.zst \
  https://mirror.cachyos.org/repo/x86_64/cachyos/cachyos-v4-mirrorlist-27-1-any.pkg.tar.zst
python /repo/scripts/force-cachyos-v4.py /etc/pacman.conf
sed -i '/^#\[multilib\]$/,+1 s/^#//' /etc/pacman.conf
test -s /etc/pacman.d/cachyos-v4-mirrorlist
pacman -Syy --noconfirm

python /repo/pipeline/tools/collect_locked_installer_packages.py \
  --calamares-root /calamares \
  --repo-root /repo \
  --output-dir /out

mkdir -p /resolver-db/local /resolver-db/sync
pacman -Sy --noconfirm --dbpath /resolver-db
mapfile -t packages < /out/top-level-packages.txt
(( ${#packages[@]} > 0 ))
pacman -Sp --noconfirm --dbpath /resolver-db \
  --print-format '%n\t%v\t%r\t%s\t%l' \
  "${packages[@]}" > /out/resolved-packages.tsv
test -s /out/resolved-packages.tsv

pacman --version > /out/pacman-version.txt
uname -m > /out/architecture.txt
(
  cd /resolver-db/sync
  sha256sum -- *.db | sort -k2
) > /out/repository-db-sha256.txt
'''
        resolver = (
            dag.container()
            .from_(_ARCH_IMAGE)
            .with_directory("/repo", source)
            .with_directory("/calamares", calamares_tree)
            .with_exec(["bash", "-lc", resolver_script])
        )

        requested = await resolver.file("/out/top-level-packages.txt").contents()
        resolved_tsv = await resolver.file("/out/resolved-packages.tsv").contents()
        source_manifest = json.loads(
            await resolver.file("/out/source-manifest.json").contents()
        )
        repository_db_sha256 = _parse_checksum_file(
            await resolver.file("/out/repository-db-sha256.txt").contents()
        )
        source_manifest["synchronized_repository_db_sha256"] = repository_db_sha256

        pacman_version = (
            await resolver.file("/out/pacman-version.txt").contents()
        ).strip()
        architecture = (
            await resolver.file("/out/architecture.txt").contents()
        ).strip()
        resolver_tool_version = {
            "pacman": pacman_version,
            "architecture": architecture,
            "repository_policy": "cachyos-v4",
            "base_image_reference": _ARCH_IMAGE,
            "dagger_engine": "v0.21.8",
        }

        return build_package_closure(
            product_spec=product.payload,
            calamares_source_lock=locked,
            explicit_requested_packages=requested,
            resolved_packages_tsv=resolved_tsv,
            resolver_tool_version=resolver_tool_version,
            source_manifest=source_manifest,
        )

    @function
    async def resolve_package_closure(
        self,
        source: dagger.Directory,
        product_spec: str,
        calamares_source_lock: str,
    ) -> str:
        """Resolve PackageClosure from the explicit ProductSpec + SourceLock boundary."""
        closure = await self._package_closure_from_lock(
            source,
            product_spec,
            calamares_source_lock,
        )
        return package_closure_json(closure)

    @function
    async def resolve_current_package_closure(self, source: dagger.Directory) -> str:
        """Resolve the current product using a freshly materialized Calamares SourceLock."""
        calamares_lock = await _resolve_git_source_lock(
            "cachyos-calamares",
            _CALAMARES_URI,
            _CALAMARES_REF,
        )
        closure = await self._package_closure_from_lock(
            source,
            default_product_spec(),
            calamares_lock,
        )
        return package_closure_json(closure)

    @function
    async def check_current_package_resolution(self, source: dagger.Directory) -> str:
        """Execute PackageClosure production and return concise immutable evidence."""
        calamares_lock = await _resolve_git_source_lock(
            "cachyos-calamares",
            _CALAMARES_URI,
            _CALAMARES_REF,
        )
        closure = await self._package_closure_from_lock(
            source,
            default_product_spec(),
            calamares_lock,
        )
        validated = validate_contract_payload("PackageClosure", closure)
        evidence = closure["resolution evidence"]
        return json.dumps(
            {
                "calamares_commit": calamares_lock["resolved_commit_or_version"],
                "calamares_content_digest": calamares_lock["content_digest"],
                "requested_package_count": evidence["requested_package_count"],
                "resolved_package_count": evidence["resolved_package_count"],
                "package_closure_digest": validated.canonical_payload_digest,
                "architecture_compatible": closure["architecture compatibility"]["compatible"],
            },
            indent=2,
            sort_keys=True,
        ) + "\n"

    @function
    async def check_contracts(self, source: dagger.Directory) -> str:
        """Run the contract/drift test suite in a hermetic container."""
        return await (
            dag.container()
            .from_("python:3.14-slim")
            .with_directory("/repo", source)
            .with_workdir("/repo")
            .with_env_variable("PYTHONPATH", "/repo/pipeline/src")
            .with_exec(
                [
                    "python",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "pipeline/tests",
                    "-v",
                ]
            )
            .stdout()
        )
