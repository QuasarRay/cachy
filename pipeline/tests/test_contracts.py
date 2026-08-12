from __future__ import annotations

from dataclasses import fields
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
SRC = PIPELINE_DIR / "src"
sys.path.insert(0, str(SRC))

from pipeline_contracts import (  # noqa: E402
    CANONICAL_CONTRACT_FIELDS,
    CONTRACT_SOURCE_SHA256,
    CONTRACT_TYPES,
    ProductSpec,
)


class ContractShapeTests(unittest.TestCase):
    def test_cross_candidate_contract_document_is_byte_for_byte_the_locked_source(self) -> None:
        path = REPO_ROOT / "docs" / "architecture" / "cross-candidate-component-contracts.md"
        digest = sha256(path.read_bytes()).hexdigest()
        self.assertEqual(CONTRACT_SOURCE_SHA256, digest)

    def test_every_contract_type_has_exactly_the_locked_field_names_and_order(self) -> None:
        self.assertEqual(set(CANONICAL_CONTRACT_FIELDS), set(CONTRACT_TYPES))
        for name, expected in CANONICAL_CONTRACT_FIELDS.items():
            actual = tuple(field.name for field in fields(CONTRACT_TYPES[name]))
            self.assertEqual(expected, actual, name)

    def test_contract_loader_rejects_missing_fields(self) -> None:
        payload = {name: None for name in CANONICAL_CONTRACT_FIELDS["ProductSpec"]}
        payload.pop("certification_policy")
        with self.assertRaisesRegex(ValueError, "certification_policy"):
            ProductSpec.from_dict(payload)

    def test_contract_loader_rejects_unknown_fields(self) -> None:
        payload = {name: None for name in CANONICAL_CONTRACT_FIELDS["ProductSpec"]}
        payload["new_convenience_field"] = "drift"
        with self.assertRaisesRegex(ValueError, "new_convenience_field"):
            ProductSpec.from_dict(payload)

    def test_round_trip_preserves_contract_payload_exactly(self) -> None:
        payload = {
            "identity_edition": {"identity": "cachyos", "edition": "lxqt-offline"},
            "architecture_policy": "x86-64-v4",
            "desktop_profile": "lxqt",
            "hardware_profile": {"gpu": "nvidia"},
            "software_bundles": ["base", "developer"],
            "filesystem_bootloader_policy": {"filesystem": "btrfs"},
            "offline_install_requirement": True,
            "certification_policy": {"no_nic": True},
        }
        contract = ProductSpec.from_dict(payload)
        self.assertEqual(payload, contract.to_dict())

    def test_metadata_digest_is_stable_under_nested_mapping_order(self) -> None:
        left = {
            "identity_edition": {"identity": "cachyos", "edition": "lxqt"},
            "architecture_policy": {"a": 1, "b": 2},
            "desktop_profile": "lxqt",
            "hardware_profile": {},
            "software_bundles": [],
            "filesystem_bootloader_policy": {},
            "offline_install_requirement": True,
            "certification_policy": {},
        }
        right = json.loads(json.dumps(left))
        right["architecture_policy"] = {"b": 2, "a": 1}
        self.assertEqual(
            ProductSpec.from_dict(left).metadata_digest(),
            ProductSpec.from_dict(right).metadata_digest(),
        )

    def test_contract_values_must_be_json_serializable(self) -> None:
        payload = {name: None for name in CANONICAL_CONTRACT_FIELDS["ProductSpec"]}
        payload["software_bundles"] = object()
        with self.assertRaises(TypeError):
            ProductSpec.from_dict(payload).to_dict()


if __name__ == "__main__":
    unittest.main()
