#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "usage: $0 ISO SOURCE_REPOSITORY_DIR" >&2
  exit 64
fi

iso=$(realpath "$1")
source_repo=$(realpath "$2")
source_db="$source_repo/cachyos-lxqt-offline.db.tar.zst"
source_sums="$source_repo/SHA256SUMS"

[[ -s "$iso" ]] || { echo "ISO not found or empty: $iso" >&2; exit 1; }
[[ -s "$source_db" ]] || { echo "source repository DB missing: $source_db" >&2; exit 1; }
[[ -s "$source_sums" ]] || { echo "source checksum manifest missing: $source_sums" >&2; exit 1; }

for cmd in mount umount mountpoint unsquashfs tar awk grep find sort sha256sum cmp realpath; do
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

sfs_cat var/cache/pacman/pkg/cachyos-lxqt-offline.db.tar.zst "$tmp_dir/repo.db.tar.zst"
sfs_cat var/cache/pacman/pkg/SHA256SUMS "$tmp_dir/SHA256SUMS"

cmp -s "$source_db" "$tmp_dir/repo.db.tar.zst" || {
  echo "repository DB embedded in ISO differs from the exact pre-build repository DB" >&2
  exit 1
}
cmp -s "$source_sums" "$tmp_dir/SHA256SUMS" || {
  echo "package checksum manifest embedded in ISO differs from the exact pre-build manifest" >&2
  exit 1
}

unsquashfs -ll "$rootfs" var/cache/pacman/pkg >"$tmp_dir/cache-listing.txt"
awk '/squashfs-root\/var\/cache\/pacman\/pkg\// { name=$NF; sub(/^.*\//, "", name); if (name != "") print name }' \
  "$tmp_dir/cache-listing.txt" | sort -u >"$tmp_dir/cache-files.txt"

expected_archives=0
while read -r digest filename; do
  [[ -n "${digest:-}" && -n "${filename:-}" ]] || continue
  filename=${filename#\*}
  [[ "$filename" != */* ]] || {
    echo "unexpected path in embedded SHA256SUMS: $filename" >&2
    exit 1
  }
  if ! grep -Fxq "$filename" "$tmp_dir/cache-files.txt"; then
    echo "package archive named by embedded SHA256SUMS is absent from ISO: $filename" >&2
    exit 1
  fi
  ((expected_archives += 1))
done <"$tmp_dir/SHA256SUMS"
(( expected_archives > 0 )) || { echo "embedded SHA256SUMS contains no package archives" >&2; exit 1; }

mkdir -p "$tmp_dir/repo-db"
tar --zstd -xf "$tmp_dir/repo.db.tar.zst" -C "$tmp_dir/repo-db"
find "$tmp_dir/repo-db" -type f -name desc \
  -exec awk '$0 == "%NAME%" { getline; print }' {} + | sort -u >"$tmp_dir/repo-package-names.txt"
repo_package_count=$(wc -l <"$tmp_dir/repo-package-names.txt")
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

  archive=$(awk -v p="$pkg" '$2 ~ ("^" p "-") && $2 ~ /\.pkg\.tar\.zst$/ { print $2; exit }' "$tmp_dir/SHA256SUMS")
  [[ -n "$archive" ]] || {
    echo "required external package archive missing from embedded SHA256SUMS: $pkg" >&2
    exit 1
  }
  sfs_cat "var/cache/pacman/pkg/$archive" "$tmp_dir/$archive"
  expected_digest=$(awk -v f="$archive" '$2 == f { print $1; exit }' "$source_sums")
  actual_digest=$(sha256sum "$tmp_dir/$archive" | awk '{print $1}')
  [[ -n "$expected_digest" && "$actual_digest" == "$expected_digest" ]] || {
    echo "embedded external package checksum mismatch: $pkg" >&2
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

sha256sum "$iso"
echo "Verified finished ISO artifact:"
echo "  embedded repository packages: $repo_package_count"
echo "  package archives named by checksum manifest: $expected_archives"
echo "  exact repository DB: matches pre-build source"
echo "  exact checksum manifest: matches pre-build source"
echo "  external package payloads: checksum verified"
echo "  zero-network Calamares overlay: present in final live root"
echo "  LXQt desktop default: present in final live root"
