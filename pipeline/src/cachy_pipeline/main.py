from __future__ import annotations

import json

import dagger
from dagger import dag, function, object_type

from .components import architecture_manifest, validate_component_boundaries
from .contracts import contract_manifest_json, validate_contract_payload
from .source_locker import (
    build_git_source_lock,
    parse_git_resolution_evidence,
    source_lock_json,
    validate_git_source_request,
)


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

    @function
    async def lock_git_source(
        self,
        source_name: str,
        retrieval_uri: str,
        requested_ref: str,
    ) -> str:
        """Resolve one Git ref and emit the exact SourceLock contract as JSON."""
        source_name, requested_ref, retrieval_uri = validate_git_source_request(
            source_name=source_name,
            requested_ref=requested_ref,
            retrieval_uri=retrieval_uri,
        )

        resolver = r"""
set -eu
apk add --no-cache git ca-certificates openssh-client >/dev/null
mkdir -p /work

git init -q /work/repo
git -C /work/repo remote add origin "$RETRIEVAL_URI"
git -C /work/repo fetch --depth=1 --force origin "$REQUESTED_REF" >/dev/null 2>&1
resolved="$(git -C /work/repo rev-parse 'FETCH_HEAD^{commit}')"
content="$(git -C /work/repo archive --format=tar "$resolved" | sha256sum | cut -d ' ' -f1)"
toolchain="$(
  {
    printf 'dagger_engine=v0.21.8\n'
    git --version
    apk info -e -v git ca-certificates openssh-client
    sha256sum "$(command -v git)"
    sha256sum "$(command -v busybox)"
    sha256sum "$(command -v ssh)"
    sha256sum /etc/ssl/certs/ca-certificates.crt
  } | sha256sum | cut -d ' ' -f1
)"
retrieved="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

printf 'resolved_commit_or_version=%s\n' "$resolved"
printf 'content_digest=sha256:%s\n' "$content"
printf 'toolchain_digest=sha256:%s\n' "$toolchain"
printf 'retrieved_at=%s\n' "$retrieved"
"""
        stdout = await (
            dag.container()
            .from_("alpine:3.22")
            .with_env_variable("RETRIEVAL_URI", retrieval_uri)
            .with_env_variable("REQUESTED_REF", requested_ref)
            .with_exec(["sh", "-c", resolver])
            .stdout()
        )
        evidence = parse_git_resolution_evidence(stdout)
        lock = build_git_source_lock(
            source_name=source_name,
            requested_ref=requested_ref,
            retrieval_uri=retrieval_uri,
            resolved_commit_or_version=evidence["resolved_commit_or_version"],
            content_digest=evidence["content_digest"],
            toolchain_digest=evidence["toolchain_digest"],
            retrieved_at=evidence["retrieved_at"],
        )
        return source_lock_json(lock)
