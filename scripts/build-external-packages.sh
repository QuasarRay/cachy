#!/usr/bin/env bash
set -euo pipefail

OUT=${1:?output directory required}
AMNEZIA_RUN=${2:?Amnezia installer path required}
mkdir -p "$OUT"
OUT=$(realpath "$OUT")
AMNEZIA_RUN=$(realpath "$AMNEZIA_RUN")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if ! id builder >/dev/null 2>&1; then
  useradd -m builder
fi

# mktemp creates the parent as 0700/root. makepkg intentionally runs as the
# unprivileged builder user, so it must be able to traverse this parent.
chmod 0755 "$WORK"

download_github_asset() {
  local repo=$1 jqexpr=$2 dest=$3
  local url
  url=$(curl -fsSL "https://api.github.com/repos/${repo}/releases/latest" | jq -r "$jqexpr" | head -n1)
  test -n "$url" && test "$url" != null
  curl -fL --retry 5 "$url" -o "$dest"
}

make_pkg() {
  local dir=$1
  chown -R builder:builder "$dir"
  install -d -m 0755 -o builder -g builder \
    "$dir/src" "$dir/.build" "$dir/.pkgdest"
  (
    cd "$dir"
    sudo -u builder env \
      SRCDEST="$dir/src" \
      BUILDDIR="$dir/.build" \
      PKGDEST="$dir/.pkgdest" \
      makepkg --noconfirm --clean --cleanbuild
  )
  cp "$dir/.pkgdest"/*.pkg.tar.zst "$OUT/"
}

# Windscribe: official upstream native Arch package.
download_github_asset Windscribe/Desktop-App '.assets[] | select(.name|endswith("_amd64.pkg.tar.zst")) | .browser_download_url' "$OUT/windscribe.pkg.tar.zst"

# sing-box: official upstream native Arch package.
download_github_asset SagerNet/sing-box '.assets[] | select(.name|test("linux_x86_64.*pkg.tar.zst$")) | .browser_download_url' "$OUT/sing-box.pkg.tar.zst"

# Xray: wrap official release archive as a local Arch package.
XR="$WORK/xray"; mkdir -p "$XR/src"
XR_JSON=$(curl -fsSL https://api.github.com/repos/XTLS/Xray-core/releases/latest)
XR_VER=$(jq -r .tag_name <<<"$XR_JSON" | sed 's/^v//')
XR_URL=$(jq -r '.assets[] | select(.name=="Xray-linux-64.zip") | .browser_download_url' <<<"$XR_JSON")
curl -fL --retry 5 "$XR_URL" -o "$XR/src/xray.zip"
cat > "$XR/PKGBUILD" <<EOF
pkgname=xray-offline
pkgver=${XR_VER//-/_}
pkgrel=1
pkgdesc='Xray-core bundled from the official upstream release for the offline CachyOS image'
arch=('x86_64')
url='https://github.com/XTLS/Xray-core'
license=('MPL-2.0')
source=('xray.zip')
sha256sums=('$(sha256sum "$XR/src/xray.zip" | cut -d' ' -f1)')
package() {
  bsdtar -xf xray.zip
  install -Dm755 xray "\$pkgdir/usr/bin/xray"
  install -d "\$pkgdir/usr/share/xray" "\$pkgdir/etc/xray"
  test ! -f geoip.dat || install -Dm644 geoip.dat "\$pkgdir/usr/share/xray/geoip.dat"
  test ! -f geosite.dat || install -Dm644 geosite.dat "\$pkgdir/usr/share/xray/geosite.dat"
  printf '%s\n' '{"log":{"loglevel":"warning"},"inbounds":[],"outbounds":[{"protocol":"freedom"}]}' > "\$pkgdir/etc/xray/config.json"
  install -d "\$pkgdir/usr/lib/systemd/system"
  cat > "\$pkgdir/usr/lib/systemd/system/xray.service" <<'UNIT'
[Unit]
Description=Xray Service
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/usr/bin/xray run -config /etc/xray/config.json
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
}
EOF
make_pkg "$XR"

# Microsoft Visual Studio Code: official stable Linux binary distribution.
VC="$WORK/vscode"; mkdir -p "$VC/src"
VC_VER=$(curl -fsSL https://update.code.visualstudio.com/api/releases/stable | jq -r '.[0]')
curl -fL --retry 5 "https://update.code.visualstudio.com/${VC_VER}/linux-x64/stable" -o "$VC/src/vscode.tar.gz"
cat > "$VC/PKGBUILD" <<EOF
pkgname=visual-studio-code-offline
pkgver=${VC_VER//-/_}
pkgrel=1
pkgdesc='Microsoft Visual Studio Code stable binary for the offline CachyOS image'
arch=('x86_64')
url='https://code.visualstudio.com/'
license=('custom')
source=('vscode.tar.gz')
sha256sums=('$(sha256sum "$VC/src/vscode.tar.gz" | cut -d' ' -f1)')
options=('!strip')
package() {
  install -d "\$pkgdir/opt/visual-studio-code" "\$pkgdir/usr/bin" "\$pkgdir/usr/share/applications"
  cp -a VSCode-linux-x64/. "\$pkgdir/opt/visual-studio-code/"
  ln -s /opt/visual-studio-code/bin/code "\$pkgdir/usr/bin/code"
  cat > "\$pkgdir/usr/share/applications/visual-studio-code.desktop" <<'DESKTOP'
[Desktop Entry]
Name=Visual Studio Code
Comment=Code Editing. Redefined.
Exec=/usr/bin/code %F
Icon=/opt/visual-studio-code/resources/app/resources/linux/code.png
Type=Application
Terminal=false
Categories=Development;IDE;
MimeType=text/plain;
DESKTOP
}
EOF
make_pkg "$VC"

# Tor Browser: official stable Linux archive, OpenPGP verified before packaging.
TB="$WORK/torbrowser"; mkdir -p "$TB/src"
TB_JSON=$(curl -fsSL https://aus1.torproject.org/torbrowser/update_3/release/download-linux-x86_64.json)
TB_VER=$(jq -r .version <<<"$TB_JSON")
TB_URL=$(jq -r .binary <<<"$TB_JSON")
TB_SIG=$(jq -r .sig <<<"$TB_JSON")
curl -fL --retry 5 "$TB_URL" -o "$TB/src/tor-browser.tar.xz"
curl -fL --retry 5 "$TB_SIG" -o "$TB/src/tor-browser.tar.xz.asc"
GNUPGHOME="$WORK/gnupg"; export GNUPGHOME; mkdir -m700 "$GNUPGHOME"
gpg --batch --auto-key-locate nodefault,wkd --locate-keys torbrowser@torproject.org
gpg --batch --verify "$TB/src/tor-browser.tar.xz.asc" "$TB/src/tor-browser.tar.xz"
cat > "$TB/PKGBUILD" <<EOF
pkgname=tor-browser-offline
pkgver=${TB_VER//-/_}
pkgrel=1
pkgdesc='Official Tor Browser stable archive, signature verified during ISO build'
arch=('x86_64')
url='https://www.torproject.org/'
license=('MPL-2.0')
source=('tor-browser.tar.xz')
sha256sums=('$(sha256sum "$TB/src/tor-browser.tar.xz" | cut -d' ' -f1)')
options=('!strip')
package() {
  install -d "\$pkgdir/opt/tor-browser" "\$pkgdir/usr/share/applications"
  cp -a tor-browser/. "\$pkgdir/opt/tor-browser/"
  cat > "\$pkgdir/usr/share/applications/tor-browser.desktop" <<'DESKTOP'
[Desktop Entry]
Name=Tor Browser
Exec=/opt/tor-browser/start-tor-browser.desktop --detach
Icon=/opt/tor-browser/Browser/browser/chrome/icons/default/default128.png
Type=Application
Terminal=false
Categories=Network;WebBrowser;Security;
DESKTOP
}
EOF
make_pkg "$TB"

# Amnezia: package the official source-built Qt IFW installer and perform the
# local installation automatically on first boot. No network is needed.
AM="$WORK/amnezia"; mkdir -p "$AM/src"; cp "$AMNEZIA_RUN" "$AM/src/AmneziaVPN.run"; chmod +x "$AM/src/AmneziaVPN.run"
cat > "$AM/PKGBUILD" <<EOF
pkgname=amnezia-vpn-offline
pkgver=4.8.21.0
pkgrel=1
pkgdesc='Official-source-built Amnezia VPN installer for offline first-boot installation'
arch=('x86_64')
url='https://github.com/amnezia-vpn/amnezia-client'
license=('GPL-3.0-only')
source=('AmneziaVPN.run')
sha256sums=('$(sha256sum "$AM/src/AmneziaVPN.run" | cut -d' ' -f1)')
options=('!strip')
package() {
  install -Dm755 AmneziaVPN.run "\$pkgdir/usr/lib/amnezia-offline/AmneziaVPN.run"
  install -d "\$pkgdir/usr/lib/systemd/system"
  cat > "\$pkgdir/usr/lib/systemd/system/amnezia-offline-install.service" <<'UNIT'
[Unit]
Description=Install bundled Amnezia VPN client
After=local-fs.target
ConditionPathExists=!/var/lib/amnezia-offline-installed
[Service]
Type=oneshot
Environment=QT_QPA_PLATFORM=offscreen
ExecStart=/bin/sh -c '/usr/lib/amnezia-offline/AmneziaVPN.run --root /opt/AmneziaVPN --accept-licenses --default-answer --confirm-command install && touch /var/lib/amnezia-offline-installed'
[Install]
WantedBy=multi-user.target
UNIT
  install -d "\$pkgdir/usr/lib/systemd/system/multi-user.target.wants"
  ln -s ../amnezia-offline-install.service "\$pkgdir/usr/lib/systemd/system/multi-user.target.wants/amnezia-offline-install.service"
}
EOF
make_pkg "$AM"

# Normalize official package filenames and record provenance.
for f in "$OUT"/windscribe.pkg.tar.zst "$OUT"/sing-box.pkg.tar.zst; do
  bsdtar -xOf "$f" .PKGINFO >/dev/null
  realname=$(bsdtar -xOf "$f" .PKGINFO | awk -F' = ' '$1=="pkgname"{n=$2} $1=="pkgver"{v=$2} END{print n "-" v "-x86_64.pkg.tar.zst"}')
  mv "$f" "$OUT/$realname"
done

(
  cd "$OUT"
  sha256sum -- *.pkg.tar.zst | sort -k2 > EXTERNAL-SHA256SUMS
  repo-add custom-external.db.tar.zst ./*.pkg.tar.zst
)
