# P0 finding: archiso deletes the embedded pacman cache before SquashFS creation

## Observed failure

The previous ISO build copied the offline repository into `airootfs/var/cache/pacman/pkg` and reported success. Independent artifact certification later extracted the finished ISO and found no `cachyos-lxqt-offline.db.tar.zst` in that path.

## Root cause

Current upstream `mkarchiso` calls `_cleanup_pacstrap_dir` after custom rootfs/package work and before `_prepare_airootfs_image`. That cleanup explicitly deletes every file beneath `${pacstrap_dir}/var/cache/pacman/pkg`. The old pipeline therefore placed product-critical repository bytes in a directory that archiso intentionally treats as disposable build cache.

This explains the historical false green: the build-workspace cache existed and was valid, but the final `airootfs.sfs` was created only after those files were removed.

## Required invariant

The offline repository is product data, not transient pacman cache. It must live at a path outside archiso's cleanup set. The active build uses:

```text
/opt/cachyos-offline-repo
```

`/etc/pacman-offline.conf` must contain:

```text
CacheDir = /opt/cachyos-offline-repo
Server = file:///opt/cachyos-offline-repo
```

Calamares activates that config only for installation. The host-side pacstrap wrapper then installs into the target root while reading repository bytes from the live system.

## Gates

Before `mkarchiso`:

- require the cleanup-safe directory to contain the expected repository DB and SHA-256 manifest;
- require exactly the expected package payload count;
- verify every payload against `SHA256SUMS`;
- assert the installed `mkarchiso` contains its `/var/cache/pacman/pkg` cleanup rule;
- assert the product repository path is not under that cleanup directory.

After `mkarchiso`, on a fresh runner:

- extract `arch/x86_64/airootfs.sfs` directly from the ISO in userspace;
- extract `/opt/cachyos-offline-repo` from SquashFS;
- verify `SHA256SUMS` and every repository DB package hash against the actual embedded bytes;
- verify Calamares points to the same cleanup-safe `file://` repository path.

A successful image build is not accepted unless this independent certification passes.
