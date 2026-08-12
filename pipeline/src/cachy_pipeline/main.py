from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import dagger
from dagger import dag, function, object_type

from .components import architecture_manifest, validate_component_boundaries
from .contracts import contract_manifest_json, validate_contract_payload
from .source_locker import build_git_source_lock, source_lock_json

_SOURCE_LOCKER_TOOLCHAIN = (
    "cachy-source-locker-v1|dagger-engine-v0.21.8|"
    "git.ref.commit|git.commit.tree(discard_git_dir=true).digest"
)


def _source_locker_toolchain_digest() -> str:
    return "sha256:" + hashlib.sha256(_SOURCE_LOCKER_TOOLCHAIN.encode("utf-8")).hexdigest()


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
    async def lock_git_source(
        self,
        source_name: str,
        retrieval_uri: str,
        requested_ref: str,
    ) -> str:
        """Resolve a Git source once and emit an immutable SourceLock JSON artifact.

        The moving requested ref is used only to discover a commit ID. Content is
        then addressed again through that exact commit before its tree digest is
        computed, so the emitted commit and content digest cannot refer to
        different revisions if the branch moves while this function is running.
        """
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
        lock = build_git_source_lock(
            source_name=source_name,
            requested_ref=requested_ref,
            resolved_commit_or_version=resolved_commit,
            content_digest=content_digest,
            retrieval_uri=retrieval_uri,
            toolchain_digest=_source_locker_toolchain_digest(),
            retrieved_at=_utc_now_rfc3339(),
        )
        return source_lock_json(lock)

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
