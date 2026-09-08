import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReleaseTests(unittest.TestCase):
    def test_release_is_current_from_any_working_directory(self):
        with tempfile.TemporaryDirectory(prefix='quiet-manual-check-') as directory:
            result = subprocess.run([sys.executable, str(ROOT / 'build_manual.py'), '--check'],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

class ExistingComponentTests(unittest.TestCase):
    """Execute both unchanged pytest-style tests without installing pytest."""
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('legacy_minimal_tests', ROOT.parent / 'tests/test_patch_minimal_ui.py')
        cls.legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.legacy)

    def test_existing_patch_idempotence(self):
        self.legacy.test_patch_is_idempotent()

    def test_existing_patch_root(self):
        with tempfile.TemporaryDirectory(prefix='quiet-manual-legacy-') as directory:
            self.legacy.test_patch_root(Path(directory))

if __name__ == '__main__':
    unittest.main()
