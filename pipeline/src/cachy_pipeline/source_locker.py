from __future__ import annotations

from datetime import datetime
import json
import re
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse

from .contracts import ContractViolation, validate_contract_payload

SOURCE_LOCK_SCHEMA_VERSION = "1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _require_text(name: str, value: str) -> str:
    if not value or value != value.strip():
        raise ContractViolation(f"{name} must be non-empty and have no surrounding whitespace")
    if _CONTROL.search(value):
        raise ContractViolation(f"{name} must not contain control characters")
    return value


def _require_sha256(name: str, value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ContractViolation(f"{name} must be sha256:<64 lowercase hex characters>")
    return value


def _require_git_object_id(value: str) -> str:
    if not _GIT_OBJECT_ID.fullmatch(value):
        raise ContractViolation(
            "resolved_commit_or_version must be an immutable 40- or 64-hex Git object ID"
        )
    return value


def _require_retrieval_uri(value: str) -> str:
    value = _require_text("retrieval_uri", value)
    parsed = urlparse(value)
    if parsed.scheme in {"https", "http", "ssh", "git"} and parsed.netloc:
        return value
    if re.fullmatch(r"[^@\s]+@[^:\s]+:.+", value):
        return value
    raise ContractViolation(
        "retrieval_uri must be a network-retrievable Git URI (https/http/ssh/git or scp-like)"
    )


def _require_retrieved_at(value: str) -> str:
    value = _require_text("retrieved_at", value)
    if not value.endswith("Z"):
        raise ContractViolation("retrieved_at must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractViolation("retrieved_at must be a valid RFC3339 UTC timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractViolation("retrieved_at must be UTC")
    return value


def validate_git_source_request(
    *, source_name: str, requested_ref: str, retrieval_uri: str
) -> tuple[str, str, str]:
    source_name = _require_text("source_name", source_name)
    requested_ref = _require_text("requested_ref", requested_ref)
    if requested_ref.startswith("-"):
        raise ContractViolation("requested_ref must not begin with '-' for Git resolution")
    retrieval_uri = _require_retrieval_uri(retrieval_uri)
    return source_name, requested_ref, retrieval_uri


def build_git_source_lock(
    *,
    source_name: str,
    requested_ref: str,
    resolved_commit_or_version: str,
    content_digest: str,
    retrieval_uri: str,
    toolchain_digest: str,
    retrieved_at: str,
) -> Mapping[str, Any]:
    """Produce the exact SourceLock contract for one Git source."""

    source_name, requested_ref, retrieval_uri = validate_git_source_request(
        source_name=source_name,
        requested_ref=requested_ref,
        retrieval_uri=retrieval_uri,
    )
    payload = {
        "source_name": source_name,
        "requested_ref": requested_ref,
        "resolved_commit_or_version": _require_git_object_id(resolved_commit_or_version),
        "content_digest": _require_sha256("content_digest", content_digest),
        "retrieval_uri": retrieval_uri,
        "toolchain_digest": _require_sha256("toolchain_digest", toolchain_digest),
        "retrieved_at": _require_retrieved_at(retrieved_at),
        "lock_schema_version": SOURCE_LOCK_SCHEMA_VERSION,
    }
    artifact = validate_contract_payload("SourceLock", payload)
    return MappingProxyType(dict(artifact.payload))


def source_lock_json(payload: Mapping[str, Any]) -> str:
    artifact = validate_contract_payload("SourceLock", payload)
    return json.dumps(dict(artifact.payload), indent=2, ensure_ascii=False) + "\n"


def parse_git_resolution_evidence(stdout: str) -> Mapping[str, str]:
    """Parse fixed-key evidence emitted by the hermetic Git resolver."""

    expected = {
        "resolved_commit_or_version",
        "content_digest",
        "toolchain_digest",
        "retrieved_at",
    }
    parsed: dict[str, str] = {}
    for raw in stdout.splitlines():
        if not raw:
            continue
        key, separator, value = raw.partition("=")
        if not separator or key not in expected:
            raise ContractViolation(f"unexpected source-lock resolver evidence line: {raw!r}")
        if key in parsed:
            raise ContractViolation(f"duplicate source-lock resolver evidence key: {key}")
        parsed[key] = value

    missing = expected - parsed.keys()
    if missing:
        raise ContractViolation(f"missing source-lock resolver evidence: {sorted(missing)}")
    return MappingProxyType(parsed)
