from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

CONTRACT_SOURCE_SHA256 = "sha256:a94353b3a477a75c3995d116624f8d2330e526bcc1310e806e63ccbd182e028d"
HYBRID_ARCHITECTURE_REFERENCE_SHA256 = "sha256:32406711947258d1ac045ad17eb9b2396b18b333767656d1086c074dc48b0efd"

EXPECTED_CONTRACT_NAMES = (
    "ProductSpec",
    "SourceLock",
    "ResourceBudget",
    "SoftwarePackage",
    "PackageClosure",
    "RepoSnapshot",
    "InstallerAdapterCertification",
    "InstallerOverlay",
    "ImageCandidate",
    "ImageCertification",
    "FailureEvidence",
)

_REFERENCE_PACKAGE = "cachy_pipeline.reference"
_CONTRACT_SOURCE = "cross-candidate-component-contracts.md"
_CONTRACT_BLOCK = re.compile(
    r"^## `(?P<name>[^`]+)`\s*$.*?^```text\s*$\n(?P<fields>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)


class ContractViolation(ValueError):
    """Raised when an artifact violates a cross-candidate component contract."""


@dataclass(frozen=True, slots=True)
class ValidatedArtifact:
    """Validation envelope; it is not itself a pipeline artifact contract."""

    contract_name: str
    payload: Mapping[str, Any]
    canonical_payload_digest: str


def _reference_bytes(name: str) -> bytes:
    return resources.files(_REFERENCE_PACKAGE).joinpath(name).read_bytes()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def assert_reference_sources_unchanged() -> None:
    actual_contract = _sha256(_reference_bytes(_CONTRACT_SOURCE))
    if actual_contract != CONTRACT_SOURCE_SHA256:
        raise ContractViolation(
            "cross-candidate contract source changed without an explicit contract-baseline update: "
            f"expected {CONTRACT_SOURCE_SHA256}, got {actual_contract}"
        )


def contract_registry() -> Mapping[str, tuple[str, ...]]:
    """Parse the exact contract field labels from the pinned Markdown source."""
    assert_reference_sources_unchanged()
    text = _reference_bytes(_CONTRACT_SOURCE).decode("utf-8")
    parsed: dict[str, tuple[str, ...]] = {}
    for match in _CONTRACT_BLOCK.finditer(text):
        name = match.group("name")
        fields = tuple(
            line.strip()
            for line in match.group("fields").splitlines()
            if line.strip()
        )
        parsed[name] = fields

    if tuple(parsed) != EXPECTED_CONTRACT_NAMES:
        raise ContractViolation(
            "contract set/order drifted: "
            f"expected {EXPECTED_CONTRACT_NAMES!r}, got {tuple(parsed)!r}"
        )
    return MappingProxyType(parsed)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return _sha256(canonical_json(value).encode("utf-8"))


def contract_manifest() -> Mapping[str, tuple[str, ...]]:
    return contract_registry()


def contract_manifest_json() -> str:
    return json.dumps(
        {name: list(fields) for name, fields in contract_registry().items()},
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def validate_contract_payload(
    contract_name: str,
    payload: str | Mapping[str, Any],
) -> ValidatedArtifact:
    registry = contract_registry()
    if contract_name not in registry:
        raise ContractViolation(
            f"unknown contract {contract_name!r}; allowed: {', '.join(registry)}"
        )

    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ContractViolation(f"payload is not valid JSON: {exc}") from exc
    else:
        decoded = dict(payload)

    if not isinstance(decoded, dict):
        raise ContractViolation("contract payload must be a JSON object")

    required = registry[contract_name]
    actual = tuple(decoded.keys())
    missing = [field for field in required if field not in decoded]
    unknown = [field for field in actual if field not in required]
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing fields={missing!r}")
        if unknown:
            details.append(f"unknown fields={unknown!r}")
        raise ContractViolation(f"{contract_name} contract violation: " + "; ".join(details))

    canonical_payload = json.loads(canonical_json(decoded))
    return ValidatedArtifact(
        contract_name=contract_name,
        payload=MappingProxyType(canonical_payload),
        canonical_payload_digest=canonical_digest(canonical_payload),
    )
