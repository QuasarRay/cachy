from __future__ import annotations

import json

import dagger
from dagger import dag, function, object_type

from .components import architecture_manifest, validate_component_boundaries
from .contracts import contract_manifest_json, validate_contract_payload


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
