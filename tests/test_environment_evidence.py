import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    'evidence', Path(__file__).resolve().parents[1] / 'packaging/verify-environment-evidence.py')
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def encoded(value):
    return json.dumps(value).encode()


def manifest(files):
    return ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                   for name, data in sorted(files.items())).encode()


class EnvironmentEvidenceTests(unittest.TestCase):
    def fixture(self):
        row = {'binary:Package': 'llm-manager', 'Version': '0.1.0',
               'Architecture': 'all', 'db:Status-Status': 'installed'}
        props = [{'name': 'dpkg:' + k, 'value': v} for k, v in row.items()]
        props += [{'name': 'llm-manager:copyright-file', 'value': 'copyright/product.txt'},
                  {'name': 'llm-manager:copyright-sha256', 'value': evidence.sha(b'MIT')}]
        environment = {'inventory.json': encoded([row]), 'copyright/product.txt': b'MIT',
                       'review.json': encoded({'package_count': 1, 'missing_copyright': []}),
                       'environment.cdx.json': encoded({'bomFormat': 'CycloneDX', 'specVersion': '1.6',
                          'components': [{'version': '0.1.0', 'properties': props}]})}
        environment['SHA256SUMS'] = manifest(environment)
        files = {'environment/data/' + n: d for n, d in environment.items()}
        files.update({'summary.json': encoded({'artifact_sha256': evidence.sha(b'candidate'),
                      'installed_package': 'llm-manager', 'installed_version': '0.1.0', 'collector_exit': 0}),
                      'artifact.sha256': (evidence.sha(b'candidate') + '  /tmp/candidate.deb\n').encode(),
                      'packages-installed.tsv': b'llm-manager\t0.1.0\tall\tinstalled\n',
                      'collector.exit': b'0\n', 'dpkg-audit.log': b''})
        return files

    def verify(self, files, artifact=b'candidate', extra=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'candidate.deb').write_bytes(artifact)
            with tarfile.open(root/'evidence.tar.xz', 'w:xz') as archive:
                sealed = {**files, 'EVIDENCE-SHA256SUMS': manifest(files)}
                for name, data in sealed.items():
                    info = tarfile.TarInfo('llm-manager-phase6-sbom-gate/' + name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
                if extra is not None:
                    archive.addfile(extra)
            return evidence.verify(root/'evidence.tar.xz', root/'candidate.deb', 'llm-manager', '0.1.0')

    def test_consistent_evidence_is_verified_without_license_verdict(self):
        result = self.verify(self.fixture())
        self.assertTrue(result['integrity_verified'])
        self.assertFalse(result['license_review_complete'])

    def test_different_artifact_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Artifact hash'):
            self.verify(self.fixture(), artifact=b'other candidate')

    def test_resealed_outer_manifest_does_not_hide_inventory_disagreement(self):
        files = self.fixture()
        files['packages-installed.tsv'] = b'llm-manager\t0.2.0\tall\tinstalled\n'
        with self.assertRaisesRegex(ValueError, 'TSV and inventory differ'):
            self.verify(files)

    def test_inner_checksum_detects_changed_copyright(self):
        files = self.fixture()
        files['environment/data/copyright/product.txt'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
            self.verify(files)

    def test_checksum_coverage_and_duplicate_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage'):
            evidence.checksums({'unlisted': b'x'}, b'')
        with self.assertRaisesRegex(ValueError, 'Duplicate checksum'):
            evidence.checksums({'a': b'x'}, manifest({'a': b'x'}) * 2)

    def test_archive_traversal_links_and_duplicates_are_rejected(self):
        for path, kind in [('../escape', tarfile.REGTYPE),
                           ('llm-manager-phase6-sbom-gate/link', tarfile.SYMTYPE),
                           ('llm-manager-phase6-sbom-gate/summary.json', tarfile.REGTYPE)]:
            with self.subTest(path=path):
                info = tarfile.TarInfo(path)
                info.type = kind
                with self.assertRaises(ValueError):
                    self.verify(self.fixture(), extra=info)
