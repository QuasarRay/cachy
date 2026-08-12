from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest
from typing import get_type_hints

PIPELINE_DIR = Path(__file__).resolve().parents[1]
SRC = PIPELINE_DIR / "src"
sys.path.insert(0, str(SRC))

from pipeline_contracts.factories import (  # noqa: E402
    ImageAssembler,
    InstallerOverlayFactory,
    RepositoryFactory,
    SoftwareFactory,
)


class FactoryBoundaryTests(unittest.TestCase):
    def test_phase_one_factory_names_are_stable(self) -> None:
        self.assertEqual(
            {
                "SoftwareFactory",
                "RepositoryFactory",
                "InstallerOverlayFactory",
                "ImageAssembler",
            },
            {
                SoftwareFactory.__name__,
                RepositoryFactory.__name__,
                InstallerOverlayFactory.__name__,
                ImageAssembler.__name__,
            },
        )

    def test_factories_only_expose_build_as_the_owned_pipeline_operation(self) -> None:
        for factory in (
            SoftwareFactory,
            RepositoryFactory,
            InstallerOverlayFactory,
            ImageAssembler,
        ):
            public_callables = {
                name
                for name, value in inspect.getmembers(factory)
                if not name.startswith("_") and callable(value)
            }
            self.assertEqual({"build"}, public_callables, factory.__name__)

    def test_factory_dependency_topology_matches_the_hybrid_architecture(self) -> None:
        software = get_type_hints(SoftwareFactory.build)
        repository = get_type_hints(RepositoryFactory.build)
        installer = get_type_hints(InstallerOverlayFactory.build)
        image = get_type_hints(ImageAssembler.build)

        self.assertEqual(
            {"self", "product_spec", "source_locks", "resource_budget", "return"},
            set(inspect.signature(SoftwareFactory.build).parameters) | {"return"},
        )
        self.assertEqual(
            {"self", "package_closure", "software_packages", "return"},
            set(inspect.signature(RepositoryFactory.build).parameters) | {"return"},
        )
        self.assertEqual(
            {"self", "product_spec", "adapter_certification", "return"},
            set(inspect.signature(InstallerOverlayFactory.build).parameters) | {"return"},
        )
        self.assertEqual(
            {"self", "source_lock", "repo_snapshot", "installer_overlay", "return"},
            set(inspect.signature(ImageAssembler.build).parameters) | {"return"},
        )

        # The overlay path is independent of repository assembly until ImageAssembler joins them.
        self.assertNotIn("repo_snapshot", installer)
        self.assertNotIn("software_packages", installer)
        self.assertIn("repo_snapshot", image)
        self.assertIn("installer_overlay", image)

    def test_factory_build_annotations_are_contract_types_not_dict_results(self) -> None:
        for factory in (
            SoftwareFactory,
            RepositoryFactory,
            InstallerOverlayFactory,
            ImageAssembler,
        ):
            hints = get_type_hints(factory.build)
            self.assertNotEqual(dict, hints.get("return"), factory.__name__)


if __name__ == "__main__":
    unittest.main()
