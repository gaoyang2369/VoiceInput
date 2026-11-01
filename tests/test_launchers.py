"""Run the batch entrypoints in an isolated fixture, without GUI or network."""
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import venv
from pathlib import Path

from core import ROOT


class LauncherTests(unittest.TestCase):
    def test_normal_and_settings_entrypoints_forward_arguments(self):
        with tempfile.TemporaryDirectory(prefix='voiceinput launcher ') as directory:
            root = Path(directory)
            venv.EnvBuilder(with_pip=False).create(root / '.venv')
            for name in ('start.bat', '打开设置.bat'):
                shutil.copyfile(ROOT / name, root / name)
            # Matching dependency snapshots skip pip; this fixture cannot call API,
            # load microphones, download models or start the actual application.
            (root / 'requirements.txt').write_text('', encoding='utf-8')
            (root / '.venv' / 'installed-requirements.txt').write_text('', encoding='utf-8')
            (root / 'app.py').write_text(
                'import json, sys\nfrom pathlib import Path\n'
                'Path(__file__).with_name("args.json").write_text(json.dumps(sys.argv[1:]))\n', encoding='utf-8')
            for batch, expected in (('start.bat', []), ('打开设置.bat', ['--settings'])):
                with self.subTest(entrypoint=batch):
                    output = root / 'args.json'
                    output.unlink(missing_ok=True)
                    result = subprocess.run(['cmd.exe', '/d', '/c', batch], cwd=root,
                                            capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    deadline = time.monotonic() + 5
                    while not output.exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(output.exists(), 'Detached launcher did not start the fixture')
                    self.assertEqual(json.loads(output.read_text()), expected)
            # The detached fixture exits after writing its arguments.
            time.sleep(0.2)
