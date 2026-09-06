#!/usr/bin/python3
"""Read-only dpkg environment evidence collector; never installs packages.

Captures ALL installed packages (a dependency superset), not an inferred APT
resolution graph. Copyright text is evidence for manual review, not a license
expression or an automatic compliance verdict.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

FIELDS = ('binary:Package', 'Version', 'Architecture', 'source:Package',
          'source:Version', 'db:Status-Status', 'Pre-Depends', 'Depends', 'Provides')


def query_inventory():
    result = subprocess.run(
        ['/usr/bin/dpkg-query', '-W', '-f=' + '\t'.join('${' + f + '}' for f in FIELDS) + '\n'],
        check=True, capture_output=True, text=True, timeout=60,
        env={**os.environ, 'LC_ALL': 'C'})
    return parse_inventory(result.stdout)


def parse_inventory(raw):
    packages = []
    for line in raw.splitlines():
        values = line.split('\t')
        if len(values) != len(FIELDS):
            raise ValueError('Malformed dpkg inventory')
        item = dict(zip(FIELDS, values))
        if item['db:Status-Status'] != 'installed':
            continue
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?', values[0]):
            raise ValueError('Invalid package name')
        if not all(item[f] for f in FIELDS[:5]):
            raise ValueError('Incomplete installed package identity')
        packages.append(item)
    if not packages or len({p['binary:Package'] for p in packages}) != len(packages):
        raise ValueError('Empty or duplicate package inventory')
    return sorted(packages, key=lambda p: p['binary:Package'])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect(packages, output, system_root=Path('/')):
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / 'copyright'
    evidence.mkdir()
    components, missing = [], []
    for package in packages:
        name = package['binary:Package']
        binary_name = name.split(':')[0]
        ref = ('pkg:deb/' + quote(binary_name, safe='') + '@' +
               quote(package['Version'], safe='') + '?arch=' + quote(package['Architecture'], safe=''))
        properties = [{'name': 'dpkg:' + k, 'value': v} for k, v in package.items()]
        # Distribution documentation commonly uses symlinks to another package.
        path = system_root / 'usr/share/doc' / binary_name / 'copyright'
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to((system_root / 'usr/share').resolve())
            data = resolved.read_bytes()
            if not data:
                raise ValueError('Empty copyright')
        except (OSError, ValueError, RuntimeError):
            missing.append(name)
            properties.append({'name': 'llm-manager:copyright-status', 'value': 'missing-or-unreadable'})
        else:
            relative = 'copyright/' + name + '.txt'
            (output / relative).write_bytes(data)
            properties.extend([
                {'name': 'llm-manager:copyright-file', 'value': relative},
                {'name': 'llm-manager:copyright-sha256', 'value': digest(data)},
                {'name': 'llm-manager:copyright-source', 'value': str(resolved.relative_to(system_root))},
            ])
        components.append({'type': 'library', 'bom-ref': ref, 'purl': ref,
                           'name': binary_name, 'version': package['Version'],
                           'properties': properties})
    common = system_root / 'usr/share/common-licenses'
    (output / 'common-licenses').mkdir()
    for path in sorted(common.iterdir()):
        if path.is_file():
            (output / 'common-licenses' / path.name).write_bytes(path.read_bytes())
    (output / 'os-release').write_bytes((system_root / 'etc/os-release').read_bytes())
    bom = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
           'metadata': {'properties': [
               {'name': 'llm-manager:scope', 'value': 'all installed dpkg packages; dependency superset; no resolved edges asserted'},
               {'name': 'llm-manager:license-review', 'value': 'pending manual review of captured copyright and common-licenses'},
           ]}, 'components': components}
    (output / 'environment.cdx.json').write_text(json.dumps(bom, indent=2) + '\n')
    (output / 'inventory.json').write_text(json.dumps(packages, indent=2) + '\n')
    (output / 'review.json').write_text(json.dumps({
        'package_count': len(packages), 'missing_copyright': missing,
        'license_review_complete': False, 'release_gate_complete': False,
    }, indent=2) + '\n')
    return missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New evidence directory')
    args = parser.parse_args()
    before = query_inventory()
    missing = collect(before, args.output)
    if query_inventory() != before:
        raise SystemExit('Package inventory changed during capture; discard this evidence')
    files = sorted(p for p in args.output.rglob('*') if p.is_file())
    (args.output / 'SHA256SUMS').write_text(''.join(
        digest(p.read_bytes()) + '  ' + str(p.relative_to(args.output)) + '\n' for p in files))
    print(json.dumps({'packages': len(before), 'missing_copyright': len(missing),
                      'output': str(args.output)}))
    if missing:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
