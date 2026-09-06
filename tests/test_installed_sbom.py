import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'installed_sbom', Path(__file__).resolve().parents[1] / 'packaging/collect-installed-sbom.py')
sbom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sbom)


def row(name='libqt6core6t64:amd64', status='installed'):
    return '\t'.join((name, '6.8.2+dfsg-9', 'amd64', 'qt6-base',
                      '6.8.2+dfsg-9', status, '', 'libc6 (>= 2.38)', '')) + '\n'


class InstalledSbomTests(unittest.TestCase):
    def test_identity_and_status(self):
        packages = sbom.parse_inventory(row() + row('removed', 'config-files'))
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]['source:Package'], 'qt6-base')
        for raw in ('', 'bad\n', row('../escape'), row() + row()):
            with self.assertRaises(ValueError):
                sbom.parse_inventory(raw)

    def test_copyright_symlink_hash_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = root / 'usr/share/doc/libqt6core6t64'
            doc.mkdir(parents=True)
            common = root / 'usr/share/common-licenses'
            common.mkdir()
            text = b'License: LGPL-3\nAdditional third-party notices\n'
            (common / 'LGPL-3').write_bytes(text)
            (doc / 'copyright').symlink_to('../../common-licenses/LGPL-3')
            (root / 'etc').mkdir()
            (root / 'etc/os-release').write_text('ID=debian\n')
            output = root / 'evidence'
            missing = sbom.collect(sbom.parse_inventory(row() + row('missing')), output, root)
            self.assertEqual(missing, ['missing'])
            bom = json.loads((output / 'environment.cdx.json').read_text())
            properties = {p['name']: p['value'] for p in bom['components'][0]['properties']}
            self.assertEqual(properties['llm-manager:copyright-sha256'], sbom.digest(text))
            self.assertEqual((output / properties['llm-manager:copyright-file']).read_bytes(), text)
            self.assertNotIn('dependencies', bom)
            self.assertFalse(json.loads((output / 'review.json').read_text())['license_review_complete'])
            with self.assertRaises(FileExistsError):
                sbom.collect(sbom.parse_inventory(row()), output, root)

    def test_inventory_change_does_not_seal_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            with patch('sys.argv', ['collector', '--output', str(output)]), \
                 patch.object(sbom, 'query_inventory', side_effect=[[{'version': '1'}], [{'version': '2'}]]), \
                 patch.object(sbom, 'collect', return_value=[]):
                with self.assertRaisesRegex(SystemExit, 'inventory changed'):
                    sbom.main()
            self.assertFalse((output / 'SHA256SUMS').exists())
