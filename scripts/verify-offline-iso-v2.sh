#!/usr/bin/env bash
set -euo pipefail

if (( $# != 1 )); then
  echo "usage: $0 ISO" >&2
  exit 64
fi

iso=$(realpath "$1")
[[ -s "$iso" ]] || { echo "ISO not found or empty: $iso" >&2; exit 1; }

for cmd in bsdtar unsquashfs tar awk grep find sort sha256sum realpath chmod; do
  command -v "$cmd" >/dev/null || { echo "required command missing: $cmd" >&2; exit 1; }
done

tmp_dir=$(mktemp -d)
cleanup() {
  chmod -R u+rwX "$tmp_dir" 2>/dev/null || true
  rm -rf "$tmp_dir" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

fail() {
  echo "$*" >&2
  exit 1
}

rootfs="$tmp_dir/airootfs.sfs"
echo "Extracting arch/x86_64/airootfs.sfs from finished ISO in userspace"
if ! bsdtar -xOf "$iso" arch/x86_64/airootfs.sfs >"$rootfs"; then
  fail "ISO does not contain a readable arch/x86_64/airootfs.sfs"
fi
[[ -s "$rootfs" ]] || fail "ISO root filesystem image is empty"
echo "Extracted live SquashFS: $(du -h "$rootfs" | awk '{print $1}')"

sfs_cat() {
  local path=$1
  local dest=$2
  if ! unsquashfs -cat "$rootfs" "$path" >"$dest"; then
    fail "missing or unreadable file in live SquashFS: /$path"
  fi
  [[ -s "$dest" ]] || fail "empty file in live SquashFS: /$path"
}

# archiso deletes /var/cache/pacman/pkg before generating airootfs.sfs. Product
# repository bytes therefore live under /opt where the cleanup phase does not
# treat them as disposable build cache.
mkdir -p "$tmp_dir/rootfs"
if ! unsquashfs -f -d "$tmp_dir/rootfs" "$rootfs" opt/cachyos-offline-repo >/dev/null; then
  fail "failed to extract /opt/cachyos-offline-repo from live SquashFS"
fi
repo="$tmp_dir/rootfs/opt/cachyos-offline-repo"
[[ -d "$repo" ]] || fail "finished ISO has no embedded /opt/cachyos-offline-repo directory"
[[ -s "$repo/cachyos-lxqt-offline.db.tar.zst" ]] || fail "finished ISO has no embedded offline repository database"
[[ -s "$repo/SHA256SUMS" ]] || fail "finished ISO has no embedded package SHA256SUMS manifest"
echo "Embedded cleanup-safe offline repository and checksum manifest are present"

if ! (
  cd "$repo"
  sha256sum --strict --quiet -c SHA256SUMS
); then
  fail "one or more embedded package archives fail SHA256SUMS verification"
fi
echo "Embedded package archive SHA-256 manifest is valid"

mkdir -p "$tmp_dir/repo-db"
if ! tar --zstd -xf "$repo/cachyos-lxqt-offline.db.tar.zst" -C "$tmp_dir/repo-db"; then
  fail "embedded offline repository database is unreadable"
fi

repo_package_count=0
: >"$tmp_dir/repo-package-names.txt"
while IFS= read -r desc; do
  name=$(awk '$0 == "%NAME%" { getline; print; exit }' "$desc")
  filename=$(awk '$0 == "%FILENAME%" { getline; print; exit }' "$desc")
  expected_sha=$(awk '$0 == "%SHA256SUM%" { getline; print; exit }' "$desc")

  [[ -n "$name" && -n "$filename" && -n "$expected_sha" ]] || \
    fail "repository metadata entry is missing NAME, FILENAME, or SHA256SUM: $desc"
  [[ "$filename" != */* ]] || \
    fail "repository metadata contains an unsafe package path: $filename"
  [[ -s "$repo/$filename" ]] || \
    fail "repository DB references a package archive absent from ISO: $filename"
  actual_sha=$(sha256sum "$repo/$filename" | awk '{print $1}')
  [[ "$actual_sha" == "$expected_sha" ]] || \
    fail "repository DB checksum mismatch for $name ($filename)"
  printf '%s\n' "$name" >>"$tmp_dir/repo-package-names.txt"
  ((repo_package_count += 1))
done < <(find "$tmp_dir/repo-db" -type f -name desc -print | sort)
sort -u -o "$tmp_dir/repo-package-names.txt" "$tmp_dir/repo-package-names.txt"
(( repo_package_count > 0 )) || fail "embedded repository DB contains no packages"
echo "Repository database references $repo_package_count package payloads"

external_packages=(
  windscribe-cli
  sing-box
  xray-offline
  visual-studio-code-offline
  tor-browser-offline
  amnezia-vpn-offline
)
for pkg in "${external_packages[@]}"; do
  grep -Fxq "$pkg" "$tmp_dir/repo-package-names.txt" || \
    fail "required external package missing from embedded repository DB: $pkg"
done
echo "All required external packages are indexed"

sfs_cat etc/pacman-offline.conf "$tmp_dir/pacman-offline.conf"
grep -Fqx '[cachyos-lxqt-offline]' "$tmp_dir/pacman-offline.conf" || \
  fail "offline repository stanza missing from /etc/pacman-offline.conf"
grep -Fqx 'CacheDir = /opt/cachyos-offline-repo' "$tmp_dir/pacman-offline.conf" || \
  fail "offline package cache does not point at cleanup-safe repository path"
grep -Fqx 'Server = file:///opt/cachyos-offline-repo' "$tmp_dir/pacman-offline.conf" || \
  fail "offline repository file:// server does not point at cleanup-safe repository path"

sfs_cat usr/local/bin/calamares-online.sh "$tmp_dir/calamares-online.sh"
grep -Fq 'cp /etc/pacman-offline.conf /etc/pacman.conf' "$tmp_dir/calamares-online.sh" || \
  fail "Calamares launcher does not activate offline pacman configuration"
if grep -Fq 'pacman -Sy' "$tmp_dir/calamares-online.sh"; then
  fail "live ISO launcher still performs a network package sync"
fi

sfs_cat etc/calamares/scripts/pacstrap_calamares "$tmp_dir/pacstrap_calamares"
grep -Fq 'pacman -r "$newroot" -Sy --config=/etc/pacman.conf' "$tmp_dir/pacstrap_calamares" || \
  fail "Calamares pacstrap wrapper does not use the host-resident offline repository"
if grep -Fq 'pacman --sysroot "$newroot"' "$tmp_dir/pacstrap_calamares"; then
  fail "live ISO contains the --sysroot pacstrap path that breaks host-resident file:// repository access"
fi

sfs_cat etc/calamares/modules/packagechooser_desktop.conf "$tmp_dir/packagechooser_desktop.conf"
grep -Fq 'default: LXQT-Desktop' "$tmp_dir/packagechooser_desktop.conf" || \
  fail "LXQt is not the default Calamares desktop"

sfs_cat usr/share/calamares/settings_online.conf "$tmp_dir/settings_online.conf"
if grep -Fq 'packages@online' "$tmp_dir/settings_online.conf"; then
  fail "live ISO still enables Calamares packages@online"
fi

archive_count=$(find "$repo" -maxdepth 1 -type f -name '*.pkg.tar.zst' | wc -l)
sha256sum "$iso"
echo "Verified finished ISO artifact:"
echo "  repository DB package entries: $repo_package_count"
echo "  embedded package archives: $archive_count"
echo "  all package archives: SHA256SUMS verified"
echo "  all repository DB package hashes: verified against embedded bytes"
echo "  required external packages: present"
echo "  cleanup-safe repository path: /opt/cachyos-offline-repo"
echo "  zero-network Calamares overlay: present in final live root"
echo "  LXQt desktop default: present in final live root"
