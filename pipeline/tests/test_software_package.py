from __future__ import annotations

import unittest

from cachy_pipeline.contracts import ContractViolation
from cachy_pipeline.software_package import select_exact_software_package_output


def _candidate(name: str, marker: str) -> dict[str, object]:
    return {
        "pkgname": name,
        "pkgver": "1.0-1",
        "arch": "x86_64",
        "filename": f"{name}-1.0-1-x86_64.pkg.tar.zst",
        "size_bytes": 100,
        "sha256": "sha256:" + marker * 64,
        "object_ref": f"dagger://software/{name}",
    }


class SoftwarePackageOutputSelectionTests(unittest.TestCase):
    def test_selects_intended_payload_and_classifies_debug_split(self):
        result = select_exact_software_package_output(
            expected_pkgname="xray-offline",
            candidates=[
                _candidate("xray-offline", "a"),
                _candidate("xray-offline-debug", "b"),
            ],
        )
        self.assertEqual(result["intended_payload"]["pkgname"], "xray-offline")
        self.assertEqual(
            [item["pkgname"] for item in result["ignored_incidental_payloads"]],
            ["xray-offline-debug"],
        )
        self.assertTrue(result["selection_policy"]["wildcard_promotion_forbidden"])

    def test_rejects_unexpected_non_debug_split(self):
        with self.assertRaisesRegex(ContractViolation, "unexpected package identities"):
            select_exact_software_package_output(
                expected_pkgname="xray-offline",
                candidates=[
                    _candidate("xray-offline", "a"),
                    _candidate("xray-helper", "b"),
                ],
            )

    def test_rejects_duplicate_intended_payloads(self):
        first = _candidate("xray-offline", "a")
        second = _candidate("xray-offline", "b")
        second["filename"] = "xray-offline-second.pkg.tar.zst"
        with self.assertRaisesRegex(ContractViolation, "exactly one"):
            select_exact_software_package_output(
                expected_pkgname="xray-offline",
                candidates=[first, second],
            )

    def test_rejects_missing_intended_payload(self):
        with self.assertRaisesRegex(ContractViolation, "exactly one"):
            select_exact_software_package_output(
                expected_pkgname="xray-offline",
                candidates=[_candidate("xray-offline-debug", "b")],
            )

    def test_rejects_unverified_digest_shape(self):
        candidate = _candidate("xray-offline", "a")
        candidate["sha256"] = "a" * 64
        with self.assertRaisesRegex(ContractViolation, "sha256"):
            select_exact_software_package_output(
                expected_pkgname="xray-offline",
                candidates=[candidate],
            )


if __name__ == "__main__":
    unittest.main()
