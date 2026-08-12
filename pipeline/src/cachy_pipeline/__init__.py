"""Dagger façade for the contract-first CachyOS pipeline migration."""

from __future__ import annotations

import json

import dagger
from dagger import dag, function, object_type

from pipeline_contracts import CANONICAL_CONTRACT_FIELDS, CONTRACT_SOURCE_SHA256


@object_type
class CachyPipeline:
    """Contract-preserving entrypoints for the hybrid pipeline."""

    @function
    def contract_manifest(self) -> str:
        """Return the exact persisted contract field map consumed by all factories."""
        return json.dumps(
            {
                "contract_source_sha256": CONTRACT_SOURCE_SHA256,
                "contracts": CANONICAL_CONTRACT_FIELDS,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @function
    def contract_test(self, source: dagger.Directory) -> dagger.Container:
        """Run contract-shape and factory-boundary tests inside Dagger."""
        return (
            dag.container()
            .from_("python:3.13-slim")
            .with_directory("/work", source)
            .with_workdir("/work")
            .with_exec(
                [
                    "python",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "pipeline/tests",
                    "-p",
                    "test_*.py",
                    "-v",
                ]
            )
        )
