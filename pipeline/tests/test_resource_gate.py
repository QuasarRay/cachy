from __future__ import annotations

import unittest

from cachy_pipeline.contracts import ContractViolation, contract_registry
from cachy_pipeline.package_resolver import default_product_spec
from cachy_pipeline.resource_gate import (
    default_iso_resource_budget,
    validate_host_target_isa_separation,
)


class HostTargetIsaSeparationTests(unittest.TestCase):
    def test_baseline_host_and_v4_target_are_accepted(self):
        evidence = validate_host_target_isa_separation(
            product_spec=default_product_spec(),
            host_repositories=["core", "extra", "multilib"],
            target_repositories=[
                "cachyos-v4",
                "cachyos-core-v4",
                "cachyos-extra-v4",
                "cachyos",
                "core",
                "extra",
                "multilib",
            ],
        )
        self.assertTrue(evidence["separated"])
        self.assertEqual(evidence["host_repository_policy"], "baseline-x86_64-only")

    def test_v4_host_repository_is_rejected(self):
        with self.assertRaisesRegex(ContractViolation, "must not supply host-executed"):
            validate_host_target_isa_separation(
                product_spec=default_product_spec(),
                host_repositories=["cachyos-core-v4", "core", "extra"],
                target_repositories=["cachyos-v4", "core", "extra"],
            )

    def test_v4_target_must_actually_include_v4_repository(self):
        with self.assertRaisesRegex(ContractViolation, "target profile must include"):
            validate_host_target_isa_separation(
                product_spec=default_product_spec(),
                host_repositories=["core", "extra"],
                target_repositories=["cachyos", "core", "extra"],
            )


class ResourceBudgetTests(unittest.TestCase):
    def test_default_budget_uses_exact_frozen_contract_fields(self):
        budget = default_iso_resource_budget()
        self.assertEqual(tuple(budget), contract_registry()["ResourceBudget"])

    def test_integrity_and_certification_failures_are_not_retried(self):
        policy = default_iso_resource_budget()["retry_class_policy"]
        self.assertEqual(policy["contract_or_integrity_failure"]["max_attempts"], 1)
        self.assertEqual(policy["offline_certification_failure"]["max_attempts"], 1)
        self.assertGreater(policy["transient_network"]["max_attempts"], 1)

    def test_image_budget_fails_before_expensive_stage(self):
        disk = default_iso_resource_budget()["disk_budget"]
        self.assertTrue(disk["fail_before_expensive_stage"])
        self.assertIn("RepoSnapshot_bytes", disk["formula"])


if __name__ == "__main__":
    unittest.main()
