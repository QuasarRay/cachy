#!/usr/bin/env bash
set -euo pipefail

output_dir=${1:-/etc/pacman.d}
mkdir -p "$output_dir"

work=$(mktemp -d)
cleanup() {
  rm -rf "$work"
}
trap cleanup EXIT INT TERM

fetch_exact() {
  local name=$1
  local url=$2
  local expected_sha=$3
  local member=$4
  local destination=$5
  local archive="$work/${name}.pkg.tar.zst"

  curl --fail --location --silent --show-error \
    --retry 3 --retry-all-errors --connect-timeout 15 \
    --output "$archive" "$url"

  local actual_sha
  actual_sha=$(sha256sum "$archive" | awk '{print $1}')
  if [[ "$actual_sha" != "$expected_sha" ]]; then
    echo "$name package checksum mismatch: expected $expected_sha, got $actual_sha" >&2
    exit 1
  fi

  if ! bsdtar -tf "$archive" | grep -Fxq "$member"; then
    echo "$name package does not contain expected member: $member" >&2
    echo "Package members:" >&2
    bsdtar -tf "$archive" >&2
    exit 1
  fi

  bsdtar -xOf "$archive" "$member" > "$destination"
  test -s "$destination"
  chmod 0644 "$destination"
  printf '%s  %s\n' "$actual_sha" "$name"
}

# Published CachyOS 27-1 package digests. These files are target repository
# metadata only; extracting them directly avoids installing optimized CachyOS
# host packages or enabling CachyOS repositories for CI-executed tools.
fetch_exact \
  cachyos-mirrorlist-27-1 \
  https://cdn77.cachyos.org/repo/x86_64/cachyos/cachyos-mirrorlist-27-1-any.pkg.tar.zst \
  69c6a033d45ecc105f632dcdc41528d0a2c84c927df0e2728bee2a8bd22d2015 \
  etc/pacman.d/cachyos-mirrorlist \
  "$output_dir/cachyos-mirrorlist"

fetch_exact \
  cachyos-v4-mirrorlist-27-1 \
  https://cdn77.cachyos.org/repo/x86_64/cachyos/cachyos-v4-mirrorlist-27-1-any.pkg.tar.zst \
  813ecafefb03a49dfb505ad594e1dd653c95d035661f70f4e38958cc36f409b4 \
  etc/pacman.d/cachyos-v4-mirrorlist \
  "$output_dir/cachyos-v4-mirrorlist"

test -s "$output_dir/cachyos-mirrorlist"
test -s "$output_dir/cachyos-v4-mirrorlist"

echo "Materialized pinned CachyOS mirrorlist metadata under $output_dir"
