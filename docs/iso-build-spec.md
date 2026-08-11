# CachyOS custom ISO — pre-build software specification

Status: REVIEW IN PROGRESS. This file is a design/source-of-truth document and is intentionally not consumed by the package-cache workflow yet.

## Target platform and desktop

- CachyOS x86-64-v4 target
- LXQt primary desktop
- Labwc lightweight Wayland fallback
- Plasma fallback desktop: pending final decision
- NVIDIA + Intel hybrid graphics support
- CachyOS current kernel + CachyOS LTS kernel
- Btrfs/Snapper recovery tooling
- Firefox and common desktop/network tooling from the CachyOS installer selection

## Approved additions for the final ISO/install

### Gaming / Windows compatibility

- Proton
  - Prefer a CachyOS-supported Proton-CachyOS package for offline availability.
  - Keep Steam's own Proton mechanism usable when online.
  - Exact Proton-CachyOS variant (SLR/native) to be chosen before the build manifest is changed.

### VPN / censorship-resilience / proxy stack

- Windscribe
  - Use the official Arch Linux package published by Windscribe, with vendor signature/key verification.
  - Install client, but do not auto-connect on first boot.

- Tor daemon and ecosystem
  - tor
  - torsocks
  - nyx
  - obfs4proxy
  - Snowflake client/transport if available in a suitable packaged form
  - Tor Browser or torbrowser-launcher acquisition strategy to be finalized for true offline use
  - Optional control/development tooling such as Stem to be reviewed

- Amnezia VPN
  - Include the desktop client and protocol/runtime pieces needed by the selected Linux build.
  - Exact acquisition strategy is pending because upstream Linux release packaging must be verified at build time.
  - Do not auto-connect on first boot.

- Xray ecosystem
  - Xray-core
  - official geodata/config assets required by the selected release
  - systemd service template/configuration support
  - example configurations/documentation suitable for local offline reference
  - optional GUI/controller to be selected separately rather than silently adding an unreviewed third-party frontend

- sing-box ecosystem
  - sing-box core
  - systemd service/configuration support
  - rule-set/geodata assets appropriate for the selected stable release
  - example configurations/documentation suitable for local offline reference

### Containers

- Docker Engine
- containerd / runc dependency closure
- docker-buildx
- docker-compose
- Do not enable Docker daemon automatically unless explicitly chosen later.
- Do not automatically add the primary user to the docker group; this is a security-sensitive privilege decision.

## Service policy

Network-manipulating tools must not all be enabled at boot. The ISO may contain many independent connectivity paths, but the installed system should start with a predictable network state.

Default behavior:

- NetworkManager: enabled
- Tor daemon: installed, disabled until selected/configured
- Xray: installed, disabled until selected/configured
- sing-box: installed, disabled until selected/configured
- Docker: installed, disabled until selected
- Windscribe: installed; no automatic VPN connection
- Amnezia: installed; no automatic VPN connection

Do not create competing default routes, DNS hijacks, kill switches, nftables rules, transparent proxies, or TUN interfaces during installation unless they are explicitly part of a separately reviewed profile.

## Packaging / provenance policy

For every package or binary that is not supplied by an enabled Arch/CachyOS repository:

1. Prefer an official upstream Linux artifact over an AUR binary repack where practical.
2. Pin the exact version used by the ISO build.
3. Verify an upstream signature when provided; otherwise pin and record a cryptographic checksum.
4. Record source URL/release/tag/commit and checksum in a machine-readable provenance manifest.
5. Cache the artifact in the ISO build so installation does not depend on Internet access.
6. Do not run an AUR helper on the target machine during the offline installation.

## Still under review / recommended additions

These are not yet approved merely by appearing here:

### Gaming completeness
- cachyos-gaming-meta
- cachyos-gaming-applications
- Steam
- Lutris
- Heroic Games Launcher
- Gamescope
- MangoHud / GOverlay
- GameMode
- Wine-CachyOS or Wine staging for non-Steam Windows applications
- umu-launcher

### Network resilience and troubleshooting
- wireguard-tools
- openvpn
- openconnect
- NetworkManager OpenConnect integration
- proxychains-ng
- dnscrypt-proxy
- tcpdump
- Wireshark
- nmap
- mtr
- socat
- netcat implementation
- aria2

### Container / portable development fallback
- Podman as a rootless fallback to Docker
- Distrobox

### Development workstation
- rustup / Rust toolchain
- clang / LLVM / lld
- GCC / binutils
- CMake
- Ninja
- pkgconf
- gdb
- lldb
- strace
- perf
- Vulkan headers/tools/validation layers
- Xonsh
- Starship

### Virtualization
- QEMU
- KVM/libvirt
- virt-manager
- edk2-ovmf
- swtpm

### Desktop resilience
- Plasma + KWin as an independent full desktop fallback
