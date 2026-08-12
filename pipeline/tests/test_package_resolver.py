from __future__ import annotations

import json
import unittest

from cachy_pipeline.contracts import ContractViolation, contract_registry, validate_contract_payload
from cachy_pipeline.package_resolver import (
    build_package_closure,
    default_product_spec,
    package_closure_json,
    parse_requested_packages,
    parse_resolved_packages_tsv,
)
from cachy_pipeline.source_locker import build_git_source_lock


class PackageResolverTests(unittest.TestCase):
    def _source_lock(self):
        return build_git_source_lock(
            source_name="cachyos-calamares",
            requested_ref="cachyos",
            resolved_commit_or_version="a" * 40,
            content_digest="sha256:" + "b" * 64,
            retrieval_uri="https://github.com/CachyOS/cachyos-calamares.git",
            toolchain_digest="sha256:" + "c" * 64,
            retrieved_at="2026-08-12T12:34:56Z",
        )

    def _tool_version(self) -> dict[str, str]:
        return {
            "pacman": "Pacman v7.0.0",
            "architecture": "x86_64",
            "repository_policy": "cachyos-v4",
            "base_image": "archlinux@sha256:" + "d" * 64,
        }

    def _resolved_tsv(self) -> str:
        return (
            "linux-cachyos\t6.17.0-1\tcachyos-v4\t123456\t"
            "https://mirror.example/linux-cachyos.pkg.tar.zst\n"
            "glibc\t2.42-1\tcore\t234567\t"
            "https://mirror.example/glibc.pkg.tar.zst\n"
        )

    def test_default_product_spec_emits_exact_contract_fields(self) -> None:
        payload = default_product_spec()
        self.assertEqual(tuple(payload), contract_registry()["ProductSpec"])
        self.assertTrue(payload["offline-install requirement"])
        self.assertEqual(payload["desktop profile"]["primary"], "LXQt")
        self.assertEqual(payload["architecture policy"]["target"], "x86_64-v4")

    def test_requested_packages_preserve_first_seen_order_and_dedupe(self) -> None:
        self.assertEqual(
            parse_requested_packages("linux-cachyos\nmesa\nlinux-cachyos\n"),
            ("linux-cachyos", "mesa"),
        )

    def test_requested_packages_reject_whitespace_inside_name(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "whitespace"):
            parse_requested_packages("not a package\n")

    def test_resolved_package_records_are_structured(self) -> None:
        records = parse_resolved_packages_tsv(self._resolved_tsv())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "linux-cachyos")
        self.assertEqual(records[0]["repository"], "cachyos-v4")
        self.assertEqual(records[0]["size_bytes"], 123456)

    def test_resolved_package_parser_rejects_malformed_record(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "5 tab-separated"):
            parse_resolved_packages_tsv("pkg\t1\tcore\n")

    def test_resolved_package_parser_rejects_non_integer_size(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "non-integer"):
            parse_resolved_packages_tsv(
                "pkg\t1\tcore\tlarge\thttps://mirror.example/pkg.pkg.tar.zst\n"
            )

    def test_resolved_package_parser_rejects_negative_size(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "negative"):
            parse_resolved_packages_tsv(
                "pkg\t1\tcore\t-1\thttps://mirror.example/pkg.pkg.tar.zst\n"
            )

    def test_package_closure_emits_exact_contract_fields_and_evidence(self) -> None:
        product = default_product_spec()
        source_lock = self._source_lock()
        closure = build_package_closure(
            product_spec=product,
            calamares_source_lock=source_lock,
            explicit_requested_packages="linux-cachyos\nmesa\n",
            resolved_packages_tsv=self._resolved_tsv(),
            resolver_tool_version=self._tool_version(),
            source_manifest={"network_fetches": 0},
        )
        self.assertEqual(tuple(closure), contract_registry()["PackageClosure"])
        self.assertEqual(
            closure["resolution evidence"]["product_spec_digest"],
            validate_contract_payload("ProductSpec", product).canonical_payload_digest,
        )
        self.assertEqual(
            closure["resolution evidence"]["calamares_source_lock_digest"],
            validate_contract_payload("SourceLock", source_lock).canonical_payload_digest,
        )
        self.assertEqual(closure["resolution evidence"]["requested_package_count"], 2)
        self.assertEqual(closure["resolution evidence"]["resolved_package_count"], 2)
        self.assertTrue(closure["architecture compatibility"]["compatible"])

    def test_package_closure_serialization_contains_no_orchestration_metadata(self) -> None:
        closure = build_package_closure(
            product_spec=default_product_spec(),
            calamares_source_lock=self._source_lock(),
            explicit_requested_packages="linux-cachyos\n",
            resolved_packages_tsv=self._resolved_tsv(),
            resolver_tool_version=self._tool_version(),
            source_manifest={"network_fetches": 0},
        )
        encoded = json.loads(package_closure_json(closure))
        self.assertEqual(set(encoded), set(contract_registry()["PackageClosure"]))
        self.assertNotIn("steps", encoded)
        self.assertNotIn("runner", encoded)
        self.assertNotIn("cache_key", encoded)

    def test_package_closure_rejects_wrong_resolver_architecture(self) -> None:
        tool = self._tool_version()
        tool["architecture"] = "aarch64"
        with self.assertRaisesRegex(ContractViolation, "x86_64 resolver"):
            build_package_closure(
                product_spec=default_product_spec(),
                calamares_source_lock=self._source_lock(),
                explicit_requested_packages="linux-cachyos\n",
                resolved_packages_tsv=self._resolved_tsv(),
                resolver_tool_version=tool,
                source_manifest={},
            )

    def test_package_closure_rejects_non_v4_repository_policy(self) -> None:
        tool = self._tool_version()
        tool["repository_policy"] = "cachyos"
        with self.assertRaisesRegex(ContractViolation, "cachyos-v4"):
            build_package_closure(
                product_spec=default_product_spec(),
                calamares_source_lock=self._source_lock(),
                explicit_requested_packages="linux-cachyos\n",
                resolved_packages_tsv=self._resolved_tsv(),
                resolver_tool_version=tool,
                source_manifest={},
            )


if __name__ == "__main__":
    unittest.main()
