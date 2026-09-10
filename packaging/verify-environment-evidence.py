#!/usr/bin/python3
"""Verify candidate environment evidence without extracting or executing it.

Checks integrity and internal consistency, not license compliance, a resolved
dependency graph, or the truth of observations made by the collector.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksums(files, manifest):
    entries = {}
    for line in manifest.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        require(match is not None, 'Malformed checksum line')
        digest, name = match.groups()
        require(name not in entries, 'Duplicate checksum path')
        entries[name] = digest
    require(set(entries) == set(files), 'Checksum coverage differs from file set')
    for name, data in files.items():
        require(sha(data) == entries[name], 'Checksum mismatch: ' + name)


def verify(archive, artifact, package, version):
    files, seen, total = {}, set(), 0
    prefix = 'llm-manager-phase6-sbom-gate/'
    with tarfile.open(archive, 'r:xz') as source:
        for member in source:
            name = member.name.rstrip('/')
            require(name not in seen, 'Duplicate archive path')
            seen.add(name)
            require(len(seen) <= 20000, 'Too many archive entries')
            require(not PurePosixPath(name).is_absolute()
                    and all(p not in ('', '.', '..') for p in name.split('/')),
                    'Unsafe archive path')
            require(name == prefix[:-1] or name.startswith(prefix), 'Unexpected archive root')
            require(member.isdir() or member.isfile(), 'Unsupported archive entry')
            if member.isdir():
                continue
            total += member.size
            require(member.size <= 32 * 1024 * 1024 and total <= 256 * 1024 * 1024,
                    'Evidence exceeds size limit')
            files[name[len(prefix):]] = source.extractfile(member).read()
    outer = files.pop('EVIDENCE-SHA256SUMS')
    checksums(files, outer)
    base = 'environment/data/'
    environment = {n[len(base):]: d for n, d in files.items() if n.startswith(base)}
    inner = environment.pop('SHA256SUMS')
    checksums(environment, inner)
    summary = json.loads(files['summary.json'])
    digest = sha(Path(artifact).read_bytes())
    require(summary['artifact_sha256'] == digest, 'Artifact hash differs from summary')
    require(files['artifact.sha256'].decode().split()[0] == digest,
            'Artifact hash differs from recorded checksum')
    require((summary['installed_package'], summary['installed_version']) == (package, version),
            'Unexpected installed package identity')
    inventory = json.loads(environment['inventory.json'])
    rows = {}
    for row in inventory:
        name = row['binary:Package']
        require(name not in rows and row['db:Status-Status'] == 'installed',
                'Duplicate or noninstalled inventory entry')
        rows[name] = row
    require(rows[package]['Version'] == version, 'Inventory package version mismatch')
    observed = {}
    for line in files['packages-installed.tsv'].decode().splitlines():
        name, ver, arch, state = line.split('\t')
        if state == 'installed':
            require(name not in observed, 'Duplicate installed TSV entry')
            observed[name] = (ver, arch)
    require(observed == {n: (r['Version'], r['Architecture']) for n, r in rows.items()},
            'TSV and inventory differ')
    bom = json.loads(environment['environment.cdx.json'])
    require((bom['bomFormat'], bom['specVersion']) == ('CycloneDX', '1.6'),
            'Unexpected BOM format')
    components, missing = {}, []
    for component in bom['components']:
        props = {p['name']: p['value'] for p in component['properties']}
        name = props['dpkg:binary:Package']
        require(name not in components, 'Duplicate BOM package')
        components[name] = component
        require({k[5:]: v for k, v in props.items() if k.startswith('dpkg:')} == rows[name],
                'BOM and inventory metadata differ')
        require(component['version'] == rows[name]['Version'], 'BOM version mismatch')
        if 'llm-manager:copyright-file' in props:
            data = environment[props['llm-manager:copyright-file']]
            require(sha(data) == props['llm-manager:copyright-sha256'], 'Copyright hash mismatch')
        else:
            require(props.get('llm-manager:copyright-status') == 'missing-or-unreadable',
                    'Unrecorded copyright status')
            missing.append(name)
    require(set(components) == set(rows), 'BOM inventory coverage differs')
    review = json.loads(environment['review.json'])
    require(review['package_count'] == len(rows)
            and sorted(review['missing_copyright']) == sorted(missing), 'Review totals differ')
    code = 2 if missing else 0
    require(summary['collector_exit'] == code and int(files['collector.exit']) == code,
            'Collector exit differs from missing copyright result')
    require(not files['dpkg-audit.log'].strip(), 'dpkg audit reported problems')
    return {'archive': Path(archive).name, 'artifact_sha256': digest,
            'package_count': len(rows), 'missing_copyright': sorted(missing),
            'integrity_verified': True, 'license_review_complete': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--package', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    try:
        result = verify(args.archive, args.artifact, args.package, args.version)
    except (ValueError, KeyError, OSError, tarfile.TarError) as exc:
        parser.exit(1, 'Evidence rejected: ' + str(exc) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
