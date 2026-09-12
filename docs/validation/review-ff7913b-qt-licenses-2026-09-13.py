"""Compare Qt/PySide6 package copyright evidence for the ff7913b environments."""
import hashlib
import json
from pathlib import Path
import re
import tarfile


REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/qt-license-review-ff7913b-2026-09-13.json'
ARCHIVES = {
    'ubuntu_local': REPO / 'docs/validation/sbom-ff7913b-ubuntu-local-2026-09-13/ubuntu-local-evidence.tar.xz',
    'ubuntu_remote': REPO / 'docs/validation/sbom-ff7913b-ubuntu-remote-2026-09-13/ubuntu-remote-evidence.tar.xz',
    'debian_local': REPO / 'docs/validation/sbom-ff7913b-debian-local-2026-09-13/debian-local-evidence.tar.xz',
}
SOURCES = {
    'pyside6',
    'qt6-base',
    'qt6-declarative',
    'qt6-svg',
    'qt6-translations',
    'qt6-wayland',
}
PREFIX = 'llm-manager-phase6-sbom-gate/environment/data/'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_member(archive, relative):
    member = archive.extractfile(PREFIX + relative)
    assert member is not None
    return member.read()


def primary_license(text):
    match = re.search(r'^Files: \*\n(?:(?!^Files: ).)*?^License: ([^\n]+)$', text, re.M | re.S)
    assert match is not None
    return match.group(1)


def inspect(path):
    with tarfile.open(path, 'r:xz') as archive:
        inventory = json.loads(read_member(archive, 'inventory.json'))
        bom = json.loads(read_member(archive, 'environment.cdx.json'))
        components = {}
        for component in bom['components']:
            properties = {item['name']: item['value'] for item in component['properties']}
            components[properties['dpkg:binary:Package']] = properties
        relevant = [row for row in inventory if row['source:Package'] in SOURCES]
        assert len(relevant) == 25
        assert {row['source:Package'] for row in relevant} == SOURCES
        sources = {}
        for source in sorted(SOURCES):
            rows = [row for row in relevant if row['source:Package'] == source]
            versions = sorted({row['source:Version'] for row in rows})
            assert len(versions) == 1
            texts = {}
            binaries = []
            for row in rows:
                name = row['binary:Package']
                properties = components[name]
                relative = properties['llm-manager:copyright-file']
                data = read_member(archive, relative)
                assert sha(data) == properties['llm-manager:copyright-sha256']
                texts[sha(data)] = data.decode('utf-8')
                binaries.append({
                    'package': name,
                    'binary_version': row['Version'],
                    'copyright_sha256': sha(data),
                })
            assert len(texts) == 1
            text = next(iter(texts.values()))
            sources[source] = {
                'source_version': versions[0],
                'binary_packages': sorted(binaries, key=lambda item: item['package']),
                'copyright_sha256': next(iter(texts)),
                'primary_files_license': primary_license(text),
                'license_stanza_names': sorted(set(re.findall(r'^License: ([^\n]+)$', text, re.M))),
                'qt_company_gpl_exception_1_0_text_present': (
                    'The Qt Company GPL Exception 1.0' in text
                ),
            }
        return {
            'archive': path.name,
            'archive_sha256': sha(path.read_bytes()),
            'environment_package_count': len(inventory),
            'qt_pyside_binary_package_count': len(relevant),
            'sources': sources,
        }


def main():
    environments = {name: inspect(path) for name, path in ARCHIVES.items()}
    ubuntu_local = environments['ubuntu_local']
    ubuntu_remote = environments['ubuntu_remote']
    assert ubuntu_local['sources'] == ubuntu_remote['sources']
    for environment in environments.values():
        assert environment['sources']['pyside6']['primary_files_license'] == (
            'GPL-3-EXCEPT or LGPL-3'
        )
        assert environment['sources']['pyside6'][
            'qt_company_gpl_exception_1_0_text_present'
        ]
        assert environment['sources']['qt6-base']['primary_files_license'] == (
            'LGPL-3 or GPL-2'
        )
    direct = json.loads((REPO / 'packaging/sbom/llm-manager.cdx.json').read_text())
    pyside = next(component for component in direct['components'] if component['name'] == 'PySide6')
    expression = pyside['licenses'][0]['expression']
    assert expression == 'LGPL-3.0-only OR (GPL-3.0-only WITH Qt-GPL-exception-1.0)'
    result = {
        'source_commit': 'ff7913bb97e896f7992720b9a43c2382970a5fc8',
        'direct_dependency_sbom_pyside6_expression': expression,
        'environments': environments,
        'comparisons': {
            'ubuntu_local_remote_qt_metadata_and_copyright_identical': True,
            'all_environments_have_25_qt_pyside_binary_packages': True,
            'all_selected_packages_have_copyright_evidence': True,
            'pyside_primary_license_and_exception_match_direct_sbom_summary': True,
            'license_review_complete': False,
            'reason': (
                'Captured source-level copyright includes additional file-specific terms; '
                'this comparison is evidence review, not a legal compliance verdict.'
            ),
        },
    }
    if OUT.exists():
        assert json.loads(OUT.read_text()) == result
    else:
        OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['comparisons'], sort_keys=True))


if __name__ == '__main__':
    main()
