#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

profile = Path(sys.argv[1]).resolve()
cache = Path(sys.argv[2]).resolve()
manifest = Path(sys.argv[3]).resolve()

if not profile.is_dir() or not cache.is_dir() or not manifest.is_file():
    raise SystemExit("usage: prepare-offline-profile.py PROFILE CACHE TOP_LEVEL_MANIFEST")

pkgs = []
for raw in manifest.read_text().splitlines():
    value = raw.split("#", 1)[0].strip()
    if value and value not in pkgs:
        pkgs.append(value)
for value in ["windscribe-cli", "sing-box", "xray-offline", "visual-studio-code-offline", "tor-browser-offline", "amnezia-vpn-offline"]:
    if value not in pkgs:
        pkgs.append(value)

root = profile / "airootfs"
cache_dst = root / "var/cache/pacman/pkg"
cache_dst.mkdir(parents=True, exist_ok=True)
for src in cache.glob("*"):
    if src.is_file():
        shutil.copy2(src, cache_dst / src.name)

# This configuration is activated only by our launcher immediately before
# Calamares. mkarchiso itself continues using the normal online build config.
pacman_offline = root / "etc/pacman-offline.conf"
pacman_offline.parent.mkdir(parents=True, exist_ok=True)
pacman_offline.write_text("""[options]
Architecture = x86_64 x86_64_v2 x86_64_v3 x86_64_v4
SigLevel = Optional TrustAll
LocalFileSigLevel = Optional
CacheDir = /var/cache/pacman/pkg
ParallelDownloads = 5

[cachyos-lxqt-offline]
SigLevel = Optional TrustAll
Server = file:///var/cache/pacman/pkg
""")

# All selected software is installed by pacstrap from the local repo. This
# removes the need for Calamares' later online package-update module.
module_dir = root / "etc/calamares/modules"
module_dir.mkdir(parents=True, exist_ok=True)
pacstrap = ["---", "basePackages:"] + [f"  - {p}" for p in pkgs] + [
    "postInstallFiles:",
    '  - "/etc/mkinitcpio.conf"',
    '  - "/usr/local/bin/dmcheck"',
    '  - "/usr/local/bin/remove-nvidia"',
    '  - "/etc/calamares/scripts/enable-ufw"',
    '  - "/etc/calamares/scripts/bootloader-post-setup"',
    '  - "/etc/calamares/scripts/shell-setup"',
    '  - "/etc/calamares/scripts/btrfs-installation-snapshot"',
]
(module_dir / "pacstrap.conf").write_text("\n".join(pacstrap) + "\n")

(module_dir / "welcome_online.conf").write_text("""---
showSupportUrl: true
showKnownIssuesUrl: true
requirements:
  requiredStorage: 24.0
  requiredRam: 2.5
  check: [storage, ram, power, root, screen]
  required: [ram]
geoip:
  style: none
""")

(module_dir / "shellprocess-before-online.conf").write_text("""---
dontChroot: true
timeout: 30
script:
  - command: "mkdir -p ${ROOT}/etc/pacman.d"
  - command: "cp /etc/pacman-more.conf ${ROOT}/etc/pacman.conf"
  - command: "/etc/calamares/scripts/detect-architecture ${ROOT}/etc/pacman.conf"
  - command: "cp -a /etc/pacman.d/gnupg ${ROOT}/etc/pacman.d/"
i18n:
  name: "Preparing local offline package installation"
""")

# CachyOS currently invokes pacman with --sysroot in its Calamares pacstrap
# wrapper. --sysroot relocates config paths and file:// repositories into the
# target root, which defeats this ISO's host-resident offline repository. Patch
# only that invocation back to the host-config/root-install model used by Arch's
# pacstrap: packages and repo metadata come exclusively from the live ISO cache,
# while files and the target package database are written below the target root.
pacstrap_wrapper_url = (
    "https://raw.githubusercontent.com/CachyOS/cachyos-calamares/"
    "cachyos/src/scripts/pacstrap_calamares"
)
pacstrap_wrapper_text = urllib.request.urlopen(pacstrap_wrapper_url, timeout=60).read().decode()
old_pacman_call = 'if ! pacman --sysroot "$newroot" -Sy "${pacman_args[@]}"; then'
new_pacman_call = 'if ! pacman -r "$newroot" -Sy --config=/etc/pacman.conf "${pacman_args[@]}"; then'
if pacstrap_wrapper_text.count(old_pacman_call) != 1:
    raise SystemExit("CachyOS pacstrap wrapper changed; refusing to build without revalidating offline semantics")
pacstrap_wrapper_text = pacstrap_wrapper_text.replace(old_pacman_call, new_pacman_call, 1)
pacstrap_wrapper = root / "etc/calamares/scripts/pacstrap_calamares"
pacstrap_wrapper.parent.mkdir(parents=True, exist_ok=True)
pacstrap_wrapper.write_text(pacstrap_wrapper_text)
pacstrap_wrapper.chmod(0o755)
if old_pacman_call in pacstrap_wrapper_text or new_pacman_call not in pacstrap_wrapper_text:
    raise SystemExit("failed to enforce host-only offline pacstrap semantics")

# packages@online and mirror-ranking/key-refresh are intentionally absent.
settings = """---
modules-search: [ local ]
instances:
- id: online
  module: welcome
  config: welcome_online.conf
- id: before-online
  module: shellprocess
  config: shellprocess-before-online.conf
- id: modify_mk_hook
  module: shellprocess
  config: shellprocess_modify_mk_hook.conf
- id: reset_mk_hook
  module: shellprocess
  config: shellprocess_reset_mk_hook.conf
- id: bootloader
  module: packagechooser
  config: packagechooser_bootloader.conf
- id: desktop
  module: packagechooser
  config: packagechooser_desktop.conf
- id: enable_ufw
  module: shellprocess
  config: shellprocess_enable_ufw.conf
- id: btrfs_snapshot
  module: shellprocess
  config: shellprocess_btrfs_snapshot.conf
- id: cleanup_calamares
  module: shellprocess
  config: shellprocess_cleanup_calamares.conf
sequence:
- show:
  - welcome@online
  - locale
  - keyboard
  - packagechooser@bootloader
  - partition
  - packagechooser@desktop
  - users
  - summary
- exec:
  - partition
  - zfs
  - mount
  - shellprocess@modify_mk_hook
  - shellprocess@before-online
  - pacstrap
  - machineid
  - locale
  - keyboard
  - localecfg
  - chwd
  - luksbootkeyfile
  - luksopenswaphookcfg
  - fstab
  - plymouthcfg
  - zfshostid
  - initcpiocfg
  - initcpio
  - users
  - networkcfg
  - displaymanager
  - hwclock
  - grubcfg
  - bootloader
  - shellprocess@reset_mk_hook
  - services-systemd
  - shellprocess
  - shellprocess@enable_ufw
  - shellprocess@btrfs_snapshot
  - shellprocess@cleanup_calamares
  - umount
- show:
  - finished
branding: cachyos
prompt-install: true
dont-chroot: false
oem-setup: false
disable-cancel: false
disable-cancel-during-exec: false
hide-back-and-next-during-exec: true
quit-at-end: false
"""
share = root / "usr/share/calamares"
share.mkdir(parents=True, exist_ok=True)
(share / "settings_online.conf").write_text(settings)

# Default the still-visible desktop chooser to LXQt; all packages are already
# fixed in pacstrap, but the choice is used by display-manager configuration.
chooser_src = "https://raw.githubusercontent.com/CachyOS/cachyos-calamares/cachyos/src/modules/packagechooser/packagechooser_desktop.conf"
chooser = urllib.request.urlopen(chooser_src, timeout=60).read().decode()
chooser = chooser.replace("default: KDE-Desktop", "default: LXQT-Desktop")
(module_dir / "packagechooser_desktop.conf").write_text(chooser)

launcher = root / "usr/local/bin/calamares-online.sh"
launcher.parent.mkdir(parents=True, exist_ok=True)
launcher.write_text("""#!/bin/bash
set -euo pipefail
log=/home/liveuser/cachy-install.log
sudo cp /etc/pacman-offline.conf /etc/pacman.conf
sudo pacman-key --init
sudo pacman-key --populate archlinux cachyos
inxi -F > "$log" 2>&1 || true
sudo cp /usr/share/calamares/settings_online.conf /etc/calamares/settings.conf
exec pkexec-wrapper calamares -D6 >>"$log" 2>&1
""")
launcher.chmod(0o755)

print(f"Prepared offline profile with {len(pkgs)} explicit install targets and {len(list(cache_dst.glob('*.pkg.tar.zst')))} cached package files")
