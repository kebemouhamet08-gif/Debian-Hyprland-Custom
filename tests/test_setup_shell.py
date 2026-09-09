from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parents[1]


class SetupShellTests(unittest.TestCase):
    def execute(self, command, **environment):
        env = {**os.environ, **environment}
        return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=10, check=False)

    def test_help_is_non_destructive(self):
        result = self.execute(["./install.sh", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("diagnostic", result.stdout)

    def test_historical_nova_wrapper_targets_legacy_engine(self):
        text = (ROOT / "install-deblestia-nova2.sh").read_text()
        self.assertIn("install-nova2.sh", text)
        self.assertNotIn('exec "$repo_dir/install.sh"', text)

    def test_component_manifest_scripts_exist(self):
        for line in (ROOT / "manifests/components.tsv").read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            installer = line.split("\t")[2]
            self.assertTrue((ROOT / installer).is_file(), installer)

    def test_uninstall_without_state_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(["./uninstall.sh"], XDG_STATE_HOME=directory)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Aucune installation", result.stdout)

    def test_plan_never_requires_confirmation_or_writes_state(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(["./install.sh", "plan"], XDG_STATE_HOME=directory)
            self.assertFalse((Path(directory) / "deblestia/setup").exists())
        self.assertEqual(result.returncode, 0)
        self.assertIn("aucune modification", result.stdout)


if __name__ == "__main__":
    unittest.main()
