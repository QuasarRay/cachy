#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterable


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_stanzas(text: str) -> list[dict[str, str]]:
    stanzas: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines() + ['']:
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


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def apt_metadata(specs: list[str]) -> dict[tuple[str, str], list[dict[str, str]]]:
    # Query many exact package=version specifications per apt-cache process.
    # This is semantically identical to querying them one at a time, but scales
    # to large self-contained dependency closures without thousands of process launches.
    index: dict[tuple[str, str], list[dict[str, str]]] = {}
    for batch in chunks(sorted(set(specs)), 100):
        cp = subprocess.run(
            ['apt-cache', 'show', *batch],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        # apt-cache may return nonzero if any requested version is unavailable.
        # Preserve any valid stanzas it returned; missing exact versions fail below.
        for stanza in parse_stanzas(cp.stdout):
            package = stanza.get('Package')
            version = stanza.get('Version')
            if package and version:
                index.setdefault((package, version), []).append(stanza)
    return index


def deb_fields(path: Path) -> tuple[str, str, str]:
    raw = subprocess.check_output(['dpkg-deb', '-f', str(path)], text=True)
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if line[:1].isspace() or ': ' not in line:
            continue
        key, value = line.split(': ', 1)
        fields[key] = value
    missing = [k for k in ('Package', 'Version', 'Architecture') if not fields.get(k)]
    if missing:
        raise ValueError(f'missing Debian control fields {missing}')
    return fields['Package'], fields['Version'], fields['Architecture']


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('deb_dir', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()

    candidates: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for deb in sorted(args.deb_dir.glob('*.deb')):
        try:
            package, version, arch = deb_fields(deb)
        except Exception as exc:
            failures.append({'file': deb.name, 'reason': f'could not read Package/Version/Architecture: {exc}'})
            continue
        candidates.append({
            'path': deb,
            'package': package,
            'version': version,
            'architecture': arch,
            'sha256': sha256(deb),
        })

    metadata = apt_metadata([
        f"{item['package']}={item['version']}" for item in candidates
    ])

    records: list[dict[str, object]] = []
    for item in candidates:
        deb = item['path']
        assert isinstance(deb, Path)
        package = str(item['package'])
        version = str(item['version'])
        actual = str(item['sha256'])
        stanzas = metadata.get((package, version), [])
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
            'architecture': item['architecture'],
            'size': deb.stat().st_size,
            'sha256': actual,
            'repository_filename': stanza.get('Filename'),
            'source': stanza.get('Source'),
        })

    result = {
        'schema': 2,
        'verification_algorithm': 'computed SHA256 must equal authenticated APT SHA256 for identical Package+Version',
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
