#!/usr/bin/env bash
set -euo pipefail

if (( $# != 1 )); then
  echo "usage: $0 ISO" >&2
  exit 64
fi

iso=$(realpath "$1")
[[ -s "$iso" ]] || { echo "ISO not found or empty: $iso" >&2; exit 1; }

for cmd in mount umount mountpoint unsquashfs tar awk grep find sort sha256sum realpath; do
  command -v "$cmd" >/dev/null || { echo "required command missing: $cmd" >&2; exit 1; }
done

mount_dir=$(mktemp -d)
tmp_dir=$(mktemp -d)
mounted=0
cleanup() {
  if (( mounted )) && mountpoint -q "$mount_dir"; then
    umount "$mount_dir" || true
  fi
  rmdir "$mount_dir" 2>/dev/null || true
  rm -rf "$tmp_dir"
}
trap cleanup EXIT INT TERM

mount -o loop,ro "$iso" "$mount_dir"
mounted=1

rootfs="$mount_dir/arch/x86_64/airootfs.sfs"
[[ -s "$rootfs" ]] || {
  echo "ISO does not contain arch/x86_64/airootfs.sfs" >&2
  exit 1
}

sfs_cat() {
  local path=$1
  local dest=$2
  if ! unsquashfs -cat "$rootfs" "$path" >"$dest"; then
    echo "missing or unreadable file in live SquashFS: /$path" >&2
    exit 1
  fi
  [[ -s "$dest" ]] || {
    echo "empty file in live SquashFS: /$path" >&2
    exit 1
  }
}

# Extract the finished ISO's repository once. This verifies the package bytes
# that are actually inside the artifact rather than re-checking the build workspace.
mkdir -p "$tmp_dir/rootfs"
unsquashfs -f -d "$tmp_dir/rootfs" "$rootfs" var/cache/pacman/pkg >/dev/null
repo="$tmp_dir/rootfs/var/cache/pacman/pkg"
test -d "$repo"
test -s "$repo/cachyos-lxqt-offline.db.tar.zst"
test -s "$repo/SHA256SUMS"

# The build-generated checksum manifest must validate every package archive
# embedded in the ISO.
(
  cd "$repo"
  sha256sum --strict --quiet -c SHA256SUMS
)

mkdir -p "$tmp_dir/repo-db"
tar --zstd -xf "$repo/cachyos-lxqt-offline.db.tar.zst" -C "$tmp_dir/repo-db"

repo_package_count=0
: >"$tmp_dir/repo-package-names.txt"
while IFS= read -r desc; do
  name=$(awk '$0 == "%NAME%" { getline; print; exit }' "$desc")
  filename=$(awk '$0 == "%FILENAME%" { getline; print; exit }' "$desc")
  expected_sha=$(awk '$0 == "%SHA256SUM%" { getline; print; exit }' "$desc")

  [[ -n "$name" && -n "$filename" && -n "$expected_sha" ]] || {
    echo "repository metadata entry is missing NAME, FILENAME, or SHA256SUM: $desc" >&2
    exit 1
  }
  [[ "$filename" != */* ]] || {
    echo "repository metadata contains an unsafe package path: $filename" >&2
    exit 1
  }
  [[ -s "$repo/$filename" ]] || {
    echo "repository DB references a package archive absent from ISO: $filename" >&2
    exit 1
  }
  actual_sha=$(sha256sum "$repo/$filename" | awk '{print $1}')
  [[ "$actual_sha" == "$expected_sha" ]] || {
    echo "repository DB checksum mismatch for $name ($filename)" >&2
    exit 1
  }
  printf '%s\n' "$name" >>"$tmp_dir/repo-package-names.txt"
  ((repo_package_count += 1))
done < <(find "$tmp_dir/repo-db" -type f -name desc -print | sort)
sort -u -o "$tmp_dir/repo-package-names.txt" "$tmp_dir/repo-package-names.txt"
(( repo_package_count > 0 )) || { echo "embedded repository DB contains no packages" >&2; exit 1; }

external_packages=(
  windscribe-cli
  sing-box
  xray-offline
  visual-studio-code-offline
  tor-browser-offline
  amnezia-vpn-offline
)
for pkg in "${external_packages[@]}"; do
  grep -Fxq "$pkg" "$tmp_dir/repo-package-names.txt" || {
    echo "required external package missing from embedded repository DB: $pkg" >&2
    exit 1
  }
done

sfs_cat etc/pacman-offline.conf "$tmp_dir/pacman-offline.conf"
grep -Fqx '[cachyos-lxqt-offline]' "$tmp_dir/pacman-offline.conf"
grep -Fqx 'Server = file:///var/cache/pacman/pkg' "$tmp_dir/pacman-offline.conf"

sfs_cat usr/local/bin/calamares-online.sh "$tmp_dir/calamares-online.sh"
grep -Fq 'cp /etc/pacman-offline.conf /etc/pacman.conf' "$tmp_dir/calamares-online.sh"
if grep -Fq 'pacman -Sy' "$tmp_dir/calamares-online.sh"; then
  echo "live ISO launcher still performs a network package sync" >&2
  exit 1
fi

sfs_cat etc/calamares/scripts/pacstrap_calamares "$tmp_dir/pacstrap_calamares"
grep -Fq 'pacman -r "$newroot" -Sy --config=/etc/pacman.conf' "$tmp_dir/pacstrap_calamares"
if grep -Fq 'pacman --sysroot "$newroot"' "$tmp_dir/pacstrap_calamares"; then
  echo "live ISO contains the --sysroot pacstrap path that breaks host-resident file:// repository access" >&2
  exit 1
fi

sfs_cat etc/calamares/modules/packagechooser_desktop.conf "$tmp_dir/packagechooser_desktop.conf"
grep -Fq 'default: LXQT-Desktop' "$tmp_dir/packagechooser_desktop.conf"

sfs_cat usr/share/calamares/settings_online.conf "$tmp_dir/settings_online.conf"
if grep -Fq 'packages@online' "$tmp_dir/settings_online.conf"; then
  echo "live ISO still enables Calamares packages@online" >&2
  exit 1
fi

archive_count=$(find "$repo" -maxdepth 1 -type f -name '*.pkg.tar.zst' | wc -l)
sha256sum "$iso"
echo "Verified finished ISO artifact:"
echo "  repository DB package entries: $repo_package_count"
echo "  embedded package archives: $archive_count"
echo "  all package archives: SHA256SUMS verified"
echo "  all repository DB package hashes: verified against embedded bytes"
echo "  required external packages: present"
echo "  zero-network Calamares overlay: present in final live root"
echo "  LXQt desktop default: present in final live root"
