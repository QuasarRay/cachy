from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LockedProfileSourceTests(unittest.TestCase):
    def test_profile_builder_reads_patches_from_locked_tree_without_network(self):
        repository = Path(__file__).resolve().parents[2]
        script = repository / "scripts/prepare-offline-profile.py"
        source = script.read_text()
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("raw.githubusercontent.com", source)
        self.assertNotIn("urlopen(", source)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            cache = root / "cache"
            calamares = root / "calamares"
            manifest = root / "packages.txt"
            profile.mkdir()
            cache.mkdir()
            (cache / "alpha-1-x86_64.pkg.tar.zst").write_bytes(b"fixture")
            manifest.write_text("alpha\n")

            wrapper = calamares / "src/scripts/pacstrap_calamares"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                '#!/bin/bash\n'
                'if ! pacman --sysroot "$newroot" -Sy "${pacman_args[@]}"; then\n'
                '  exit 1\n'
                'fi\n'
            )
            chooser = (
                calamares
                / "src/modules/packagechooser/packagechooser_desktop.conf"
            )
            chooser.parent.mkdir(parents=True)
            chooser.write_text("default: KDE-Desktop\n")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(profile),
                    str(cache),
                    str(manifest),
                    str(calamares),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            airootfs = profile / "airootfs"
            overlay = airootfs / "usr/local/lib/cachyos-offline-overlay/rootfs"
            patched_wrapper = (
                overlay / "etc/calamares/scripts/pacstrap_calamares"
            ).read_text()
            self.assertNotIn("pacman --sysroot", patched_wrapper)
            self.assertIn(
                'pacman -r "$newroot" -Sy --config=/etc/pacman.conf',
                patched_wrapper,
            )
            self.assertIn(
                "default: LXQT-Desktop",
                (overlay / "etc/calamares/modules/packagechooser_desktop.conf").read_text(),
            )

            offline_repo = airootfs / "opt/cachyos-offline-repo"
            self.assertTrue((offline_repo / "alpha-1-x86_64.pkg.tar.zst").is_file())
            self.assertFalse((airootfs / "var/cache/pacman/pkg").exists())

            offline_pacman = (airootfs / "etc/pacman-offline.conf").read_text()
            self.assertIn("CacheDir = /opt/cachyos-offline-repo", offline_pacman)
            self.assertIn(
                "Server = file:///opt/cachyos-offline-repo", offline_pacman
            )
            self.assertNotIn("CacheDir = /var/cache/pacman/pkg", offline_pacman)


if __name__ == "__main__":
    unittest.main()
