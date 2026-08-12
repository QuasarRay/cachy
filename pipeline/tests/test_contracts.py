from __future__ import annotations

import json
import unittest

from cachy_pipeline.components import architecture_manifest, component_boundaries
from cachy_pipeline.contracts import (
    HYBRID_ARCHITECTURE_REFERENCE_SHA256,
    CONTRACT_SOURCE_SHA256,
    ContractViolation,
    EXPECTED_CONTRACT_NAMES,
    assert_reference_sources_unchanged,
    canonical_digest,
    contract_registry,
    validate_contract_payload,
)


class ContractBaselineTests(unittest.TestCase):
    def test_reference_documents_match_frozen_baseline(self) -> None:
        self.assertTrue(CONTRACT_SOURCE_SHA256.startswith("sha256:"))
        self.assertTrue(HYBRID_ARCHITECTURE_REFERENCE_SHA256.startswith("sha256:"))
        assert_reference_sources_unchanged()

    def test_contract_set_is_exact(self) -> None:
        self.assertEqual(tuple(contract_registry()), EXPECTED_CONTRACT_NAMES)

    def test_product_spec_remains_semantic_not_orchestration(self) -> None:
        fields = contract_registry()["ProductSpec"]
        self.assertEqual(
            fields,
            (
                "identity / edition",
                "architecture policy",
                "desktop profile",
                "hardware profile",
                "software bundles",
                "filesystem / bootloader policy",
                "offline-install requirement",
                "certification policy",
            ),
        )
        forbidden = {"steps", "commands", "runner", "workflow", "pacman commands"}
        self.assertFalse(forbidden.intersection(fields))

    def test_all_component_references_are_defined_contracts(self) -> None:
        contracts = set(contract_registry())
        for boundary in component_boundaries():
            referenced = set(
                boundary.consumes + boundary.produces + boundary.owns_invariants_of
            )
            self.assertLessEqual(referenced, contracts)

    def test_producer_owns_exactly_its_output_invariants(self) -> None:
        for boundary in component_boundaries():
            self.assertEqual(
                set(boundary.owns_invariants_of),
                set(boundary.produces),
                boundary.name,
            )

    def test_undefined_software_package_set_contract_is_not_invented(self) -> None:
        self.assertNotIn("SoftwarePackageSet", contract_registry())
        serialized = json.dumps(
            {
                name: {key: list(value) for key, value in metadata.items()}
                for name, metadata in architecture_manifest().items()
            }
        )
        self.assertNotIn("SoftwarePackageSet", serialized)


class PayloadValidationTests(unittest.TestCase):
    def _valid_product_spec(self) -> dict[str, object]:
        return {
            field: f"value:{index}"
            for index, field in enumerate(contract_registry()["ProductSpec"])
        }

    def test_unknown_field_fails_closed(self) -> None:
        payload = self._valid_product_spec()
        payload["commands"] = ["pacman -Syu"]
        with self.assertRaisesRegex(ContractViolation, "unknown fields"):
            validate_contract_payload("ProductSpec", payload)

    def test_missing_field_fails_closed(self) -> None:
        payload = self._valid_product_spec()
        payload.pop("certification policy")
        with self.assertRaisesRegex(ContractViolation, "missing fields"):
            validate_contract_payload("ProductSpec", payload)

    def test_unknown_contract_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "unknown contract"):
            validate_contract_payload("SoftwarePackageSet", {})

    def test_canonical_digest_ignores_object_insertion_order(self) -> None:
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(canonical_digest(left), canonical_digest(right))

    def test_canonical_digest_changes_with_content(self) -> None:
        self.assertNotEqual(canonical_digest({"a": 1}), canonical_digest({"a": 2}))

    def test_validated_payload_is_immutable(self) -> None:
        artifact = validate_contract_payload("ProductSpec", self._valid_product_spec())
        with self.assertRaises(TypeError):
            artifact.payload["desktop profile"] = "mutated"  # type: ignore[index]

    def test_json_payload_is_accepted_with_exact_fields(self) -> None:
        payload = self._valid_product_spec()
        artifact = validate_contract_payload("ProductSpec", json.dumps(payload))
        self.assertEqual(artifact.contract_name, "ProductSpec")
        self.assertRegex(artifact.canonical_payload_digest, r"^sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
