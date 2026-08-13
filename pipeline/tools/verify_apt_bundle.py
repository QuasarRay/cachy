#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def apt_stanzas(package: str, version: str) -> list[dict[str, str]]:
    cp = subprocess.run(
        ['apt-cache', 'show', f'{package}={version}'],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode != 0:
        return []
    stanzas: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in cp.stdout.splitlines() + ['']:
        if not line.strip():
            if current:
                stanzas.append(current)
                current = {}
            continue
        if line[:1].isspace() or ': ' not in line:
            continue
        k, v = line.split(': ', 1)
        current[k] = v
    return stanzas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('deb_dir', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()

    records = []
    failures = []
    for deb in sorted(args.deb_dir.glob('*.deb')):
        fields = subprocess.check_output(
            ['dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture'],
            text=True,
        ).splitlines()
        if len(fields) != 3:
            failures.append({'file': deb.name, 'reason': 'could not read Package/Version/Architecture'})
            continue
        package, version, arch = fields
        actual = sha256(deb)
        stanzas = apt_stanzas(package, version)
        matches = [s for s in stanzas if s.get('SHA256') == actual]
        if not matches:
            failures.append({
                'file': deb.name,
                'package': package,
                'version': version,
                'actual_sha256': actual,
                'metadata_sha256_values': sorted({s.get('SHA256', '') for s in stanzas if s.get('SHA256')}),
            })
            continue
        stanza = matches[0]
        records.append({
            'file': deb.name,
            'package': package,
            'version': version,
            'architecture': arch,
            'size': deb.stat().st_size,
            'sha256': actual,
            'repository_filename': stanza.get('Filename'),
            'source': stanza.get('Source'),
        })

    result = {
        'schema': 1,
        'verified_against_signed_apt_metadata': not failures,
        'package_count': len(records),
        'records': records,
        'failures': failures,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    if failures:
        print(json.dumps(failures, indent=2))
        return 1
    print(f'Verified {len(records)} .deb files byte-for-byte against SHA256 values in authenticated APT package metadata')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
