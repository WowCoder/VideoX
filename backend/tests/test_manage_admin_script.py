import subprocess
import sys
import unittest
from pathlib import Path


class ManageAdminScriptTests(unittest.TestCase):
    def test_direct_script_entrypoint_can_import_application(self):
        backend_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/manage_admin.py", "--help"],
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OpenVMA", result.stdout)
        self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
