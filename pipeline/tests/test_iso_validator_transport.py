from __future__ import annotations

import unittest
from pathlib import Path


class IsoValidatorTransportTests(unittest.TestCase):
    def test_validator_does_not_require_loop_mounts(self):
        repository = Path(__file__).resolve().parents[2]
        source = (repository / "scripts/verify-offline-iso.sh").read_text()
        self.assertIn('bsdtar -xOf "$iso" arch/x86_64/airootfs.sfs', source)
        self.assertNotIn('mount -o loop', source)
        self.assertNotIn('losetup', source)
        self.assertIn('unsquashfs -f -d "$tmp_dir/rootfs"', source)


if __name__ == "__main__":
    unittest.main()
