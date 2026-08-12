from __future__ import annotations

import json
import unittest

from cachy_pipeline.contracts import ContractViolation, contract_registry
from cachy_pipeline.source_locker import (
    SOURCE_LOCK_SCHEMA_VERSION,
    build_git_source_lock,
    parse_git_resolution_evidence,
    source_lock_json,
    validate_git_source_request,
)


class SourceLockProducerTests(unittest.TestCase):
    def _valid(self) -> dict[str, str]:
        return {
            "source_name": "cachyos-calamares",
            "requested_ref": "cachyos",
            "resolved_commit_or_version": "a" * 40,
            "content_digest": "sha256:" + "b" * 64,
            "retrieval_uri": "https://github.com/CachyOS/cachyos-calamares.git",
            "toolchain_digest": "sha256:" + "c" * 64,
            "retrieved_at": "2026-08-12T12:34:56Z",
        }

    def test_emits_exact_cross_candidate_source_lock_fields(self) -> None:
        payload = build_git_source_lock(**self._valid())
        self.assertEqual(tuple(payload), contract_registry()["SourceLock"])
        self.assertEqual(payload["lock_schema_version"], SOURCE_LOCK_SCHEMA_VERSION)
        self.assertEqual(len(payload), 8)

    def test_serialized_lock_contains_no_orchestration_metadata(self) -> None:
        payload = build_git_source_lock(**self._valid())
        encoded = json.loads(source_lock_json(payload))
        self.assertEqual(set(encoded), set(contract_registry()["SourceLock"]))
        self.assertNotIn("steps", encoded)
        self.assertNotIn("runner", encoded)
        self.assertNotIn("cache_key", encoded)

    def test_moving_requested_ref_is_preserved_but_resolved_value_is_immutable(self) -> None:
        payload = build_git_source_lock(**self._valid())
        self.assertEqual(payload["requested_ref"], "cachyos")
        self.assertRegex(payload["resolved_commit_or_version"], r"^[0-9a-f]{40}$")

    def test_rejects_symbolic_resolved_ref(self) -> None:
        values = self._valid()
        values["resolved_commit_or_version"] = "cachyos"
        with self.assertRaisesRegex(ContractViolation, "immutable"):
            build_git_source_lock(**values)

    def test_accepts_sha256_git_object_ids_for_future_git_repositories(self) -> None:
        values = self._valid()
        values["resolved_commit_or_version"] = "d" * 64
        payload = build_git_source_lock(**values)
        self.assertEqual(payload["resolved_commit_or_version"], "d" * 64)

    def test_rejects_non_sha256_content_digest(self) -> None:
        values = self._valid()
        values["content_digest"] = "b" * 64
        with self.assertRaisesRegex(ContractViolation, "sha256"):
            build_git_source_lock(**values)

    def test_rejects_non_sha256_toolchain_digest(self) -> None:
        values = self._valid()
        values["toolchain_digest"] = "sha512:" + "c" * 64
        with self.assertRaisesRegex(ContractViolation, "sha256"):
            build_git_source_lock(**values)

    def test_rejects_local_retrieval_path(self) -> None:
        values = self._valid()
        values["retrieval_uri"] = "/tmp/repo"
        with self.assertRaisesRegex(ContractViolation, "network-retrievable"):
            build_git_source_lock(**values)

    def test_accepts_scp_like_git_uri(self) -> None:
        values = self._valid()
        values["retrieval_uri"] = "git@github.com:CachyOS/cachyos-calamares.git"
        payload = build_git_source_lock(**values)
        self.assertEqual(payload["retrieval_uri"], values["retrieval_uri"])

    def test_rejects_non_utc_retrieval_time(self) -> None:
        values = self._valid()
        values["retrieved_at"] = "2026-08-12T12:34:56+02:00"
        with self.assertRaisesRegex(ContractViolation, "ending in Z"):
            build_git_source_lock(**values)

    def test_rejects_control_characters_in_ref(self) -> None:
        values = self._valid()
        values["requested_ref"] = "main\nmalicious"
        with self.assertRaisesRegex(ContractViolation, "control"):
            build_git_source_lock(**values)

    def test_rejects_option_like_ref_before_git_resolution(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "must not begin"):
            validate_git_source_request(
                source_name="source",
                requested_ref="--upload-pack=evil",
                retrieval_uri="https://github.com/QuasarRay/cachy.git",
            )


class SourceLockEvidenceTests(unittest.TestCase):
    def test_parses_exact_resolver_evidence(self) -> None:
        evidence = parse_git_resolution_evidence(
            "resolved_commit_or_version=" + "a" * 40 + "\n"
            "content_digest=sha256:" + "b" * 64 + "\n"
            "toolchain_digest=sha256:" + "c" * 64 + "\n"
            "retrieved_at=2026-08-12T12:34:56Z\n"
        )
        self.assertEqual(set(evidence), {
            "resolved_commit_or_version",
            "content_digest",
            "toolchain_digest",
            "retrieved_at",
        })

    def test_rejects_unknown_resolver_evidence(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "unexpected"):
            parse_git_resolution_evidence("runner=ubuntu-latest\n")

    def test_rejects_missing_resolver_evidence(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "missing"):
            parse_git_resolution_evidence(
                "resolved_commit_or_version=" + "a" * 40 + "\n"
            )


if __name__ == "__main__":
    unittest.main()
