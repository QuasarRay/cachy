from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .contracts import ContractViolation

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractViolation(f"{label} must be a non-empty trimmed string")
    return value


def _candidate(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    item = dict(raw)
    size = item.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ContractViolation(f"candidate[{index}].size_bytes must be a non-negative integer")
    digest = item.get("sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ContractViolation(f"candidate[{index}].sha256 must be sha256:<64 lowercase hex>")
    filename = _text(item.get("filename"), label=f"candidate[{index}].filename")
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise ContractViolation(f"candidate[{index}].filename must be a basename")
    return {
        "pkgname": _text(item.get("pkgname"), label=f"candidate[{index}].pkgname"),
        "pkgver": _text(item.get("pkgver"), label=f"candidate[{index}].pkgver"),
        "arch": _text(item.get("arch"), label=f"candidate[{index}].arch"),
        "filename": filename,
        "size_bytes": size,
        "sha256": digest,
        "object_ref": _text(item.get("object_ref"), label=f"candidate[{index}].object_ref"),
    }


def select_exact_software_package_output(
    *,
    expected_pkgname: str,
    candidates: Iterable[Mapping[str, Any]],
    allowed_incidental_suffixes: tuple[str, ...] = ("-debug",),
) -> Mapping[str, Any]:
    """Select one intended native package and classify incidental split outputs.

    `makepkg` may emit package splits that were not requested by ProductSpec
    (for example an automatically generated `-debug` package). Artifact
    boundaries must be based on package metadata identity, never filename
    wildcards. Unexpected non-incidental packages fail closed.
    """

    expected = _text(expected_pkgname, label="expected_pkgname")
    normalized = [_candidate(raw, index) for index, raw in enumerate(candidates)]
    if not normalized:
        raise ContractViolation("SoftwarePackage builder produced no native package candidates")

    intended = [item for item in normalized if item["pkgname"] == expected]
    incidental: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []

    for item in normalized:
        name = item["pkgname"]
        if name == expected:
            continue
        if any(name == expected + suffix for suffix in allowed_incidental_suffixes):
            incidental.append(item)
        else:
            unexpected.append(item)

    if unexpected:
        raise ContractViolation(
            "SoftwarePackage builder emitted unexpected package identities: "
            f"{sorted(item['pkgname'] for item in unexpected)!r}"
        )
    if len(intended) != 1:
        raise ContractViolation(
            f"expected exactly one {expected!r} native package payload, got {len(intended)}"
        )

    return MappingProxyType(
        {
            "intended_payload": intended[0],
            "ignored_incidental_payloads": sorted(
                incidental, key=lambda item: (item["pkgname"], item["filename"])
            ),
            "selection_policy": {
                "identity_source": "native package metadata",
                "expected_pkgname": expected,
                "allowed_incidental_suffixes": list(allowed_incidental_suffixes),
                "wildcard_promotion_forbidden": True,
            },
        }
    )
