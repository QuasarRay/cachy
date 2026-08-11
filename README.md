# CachyOS LXQt offline-install cache

Personal build workspace for preparing a self-contained CachyOS LXQt installer.

Current phase: **package inventory and cache only**. The ISO is intentionally not built yet.

The cache workflow derives its top-level package set from CachyOS's current Calamares `pacstrap.conf` and `netinstall.yaml`, selects LXQt and the normally selected common groups, then adds hardware/recovery packages needed for an offline laptop installation.

Package payloads are stored only in the GitHub Actions cache, not committed to Git. Text manifests and resolved package metadata are uploaded as small workflow artifacts for review.
