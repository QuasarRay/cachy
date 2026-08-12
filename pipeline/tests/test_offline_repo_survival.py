from __future__ import annotations

import unittest
from pathlib import Path


class OfflineRepositorySurvivalTests(unittest.TestCase):
    def test_validator_requires_cleanup_safe_repo_path(self):
        repository = Path(__file__).resolve().parents[2]
        validator = (repository / "scripts/verify-offline-iso-v2.sh").read_text()
        self.assertIn("opt/cachyos-offline-repo", validator)
        self.assertNotIn('repo="$tmp_dir/rootfs/var/cache/pacman/pkg"', validator)
        self.assertIn("Server = file:///opt/cachyos-offline-repo", validator)

    def test_hardening_notes_capture_archiso_cache_deletion_hazard(self):
        repository = Path(__file__).resolve().parents[2]
        notes = (repository / "pipeline/HARDENING.md").read_text()
        self.assertIn("/var/cache/pacman/pkg", notes)
        self.assertIn("false green", notes)


if __name__ == "__main__":
    unittest.main()
