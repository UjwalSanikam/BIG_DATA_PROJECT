"""Offline failure/recovery tests; no apt or real runtime installation."""
import hashlib, io, json, pathlib, subprocess, sys, tarfile, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'vm-kit'))
import download_runtime as runtime
import prepare_python
from preflight import validate

TEST_TEMP = pathlib.Path(__file__).resolve().parents[1] / '.local'
TEST_TEMP.mkdir(exist_ok=True)

CONFIG = 'NODE=3\nN1=192.168.194.10\nN2=192.168.194.248\nN3=192.168.194.110\nN4=192.168.194.52\n'

class Installer(unittest.TestCase):
    def test_configuration_supports_different_users_but_rejects_shell_errors(self):
        self.assertEqual(validate(CONFIG)['NODE'], '3')
        self.assertEqual(validate(CONFIG + 'LAB_USER=pes1ug24cs538\n')['LAB_USER'], 'pes1ug24cs538')
        for bad in [CONFIG.replace('NODE=3', 'NODE=pes1ug24cs538'), CONFIG + 'LAB_USER=$pes1ug24cs538', CONFIG + 'LAB_USER=x;whoami', CONFIG + 'NODE=2', CONFIG.replace('192.168.194.52', '192.168.194.110')]:
            with self.assertRaises(ValueError):
                validate(bad)

    def test_download_retries_then_checks_entire_file(self):
        import urllib.error
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp:
            archive = pathlib.Path(temp) / 'file'
            with patch.object(runtime.urllib.request, 'urlopen', side_effect=[urllib.error.URLError('temporary'), io.BytesIO(b'correct')]), patch.object(runtime.time, 'sleep'):
                runtime.download('https://example.org/file', archive, hashlib.sha256(b'correct').hexdigest(), 'sha256')
            self.assertEqual(archive.read_bytes(), b'correct')

    def test_checksum_failure_never_replaces_an_existing_install(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp:
            root = pathlib.Path(temp)
            target = root / 'test'
            target.mkdir()
            (target / 'keep').write_text('existing')
            with patch.dict(runtime.ARTIFACTS, {'test': ('https://example.org/file', '0'*64, 'sha256', 'bin/tool')}), patch.object(runtime.urllib.request, 'urlopen', return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(RuntimeError, 'CHECKSUM_FAILED'):
                    runtime.install('test', root)
            self.assertEqual((target / 'keep').read_text(), 'existing')

    def test_verified_install_is_atomic_and_reused_without_network(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            info = tarfile.TarInfo('package/bin/tool')
            info.size = 4
            tar.addfile(info, io.BytesIO(b'tool'))
        data = archive.getvalue()
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp, patch.dict(runtime.ARTIFACTS, {'test': ('https://example.org/file', hashlib.sha256(data).hexdigest(), 'sha256', 'bin/tool')}):
            root = pathlib.Path(temp)
            (root / 'test').mkdir()
            (root / 'test/keep').write_text('previous')
            with patch.object(runtime.urllib.request, 'urlopen', return_value=io.BytesIO(data)):
                installed = runtime.install('test', root)
            self.assertEqual((installed / 'bin/tool').read_bytes(), b'tool')
            self.assertEqual(next(root.glob('test.previous-*/keep')).read_text(), 'previous')
            with patch.object(runtime.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network')):
                self.assertEqual(runtime.install('test', root), installed)

    def test_python314_environment_is_preserved_before_recreation(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp:
            root = pathlib.Path(temp)
            (root / 'venv').mkdir()
            (root / 'venv/keep').write_text('old environment')
            with patch.object(prepare_python, 'install', return_value=root / 'runtime/python311'), patch.object(prepare_python.subprocess, 'check_output', side_effect=['3.11.18\n', '3.14.3\n']), patch.object(prepare_python.subprocess, 'run') as create:
                prepare_python.prepare(root)
                self.assertEqual(create.call_args.args[0][-2:], ['venv', str(root / 'venv')])
            self.assertEqual(next(root.glob('venv.previous-*/keep')).read_text(), 'old environment')

    def test_python311_environment_is_reused(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as temp:
            root = pathlib.Path(temp)
            (root / 'venv').mkdir()
            with patch.object(prepare_python, 'install', return_value=root / 'runtime/python311'), patch.object(prepare_python.subprocess, 'check_output', return_value='3.11.18\n'), patch.object(prepare_python.subprocess, 'run') as create:
                prepare_python.prepare(root)
                create.assert_not_called()

if __name__ == '__main__':
    unittest.main()
