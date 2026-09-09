import json
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
from mpvpaper_engine.models import PlaybackState, PlaybackStatus  # noqa: E402
from mpvpaper_engine.paths import EnginePaths  # noqa: E402
from mpvpaper_engine.state import (  # noqa: E402
    EngineState,
    StateStore,
    read_state,
    state_from_dict,
    state_to_dict,
    write_state,
)


def temporary_paths(root):
    root = Path(root)
    return EnginePaths.from_environment({
        "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"), "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
    })


class StateTests(unittest.TestCase):
    def test_empty_state_is_safe(self):
        state = EngineState()
        self.assertEqual(state.service_status, "stopped")
        self.assertEqual(state.outputs, {})
        self.assertIsNone(state.last_error)

    def test_serialize_and_deserialize(self):
        original = EngineState(service_status="running", outputs={
            "eDP-1": PlaybackState(
                "eDP-1", status=PlaybackStatus.PLAYING,
                path=Path("/wall/a.mp4"), position=12.5,
            )
        })
        restored = state_from_dict(state_to_dict(original))
        self.assertEqual(restored.service_status, "running")
        self.assertEqual(restored.outputs["eDP-1"].path, Path("/wall/a.mp4"))
        self.assertEqual(restored.outputs["eDP-1"].position, 12.5)

    def test_atomic_write_has_no_temporary_leftover(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            write_state(EngineState(), paths)
            self.assertTrue(paths.state_file.is_file())
            self.assertEqual(list(paths.runtime_home.glob(".state.json-*")), [])

    def test_invalid_json_is_logged_and_not_destroyed(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            paths.runtime_home.mkdir(parents=True)
            damaged = "{broken\n"
            paths.state_file.write_text(damaged, encoding="utf-8")
            with self.assertLogs("mpvpaper_engine.state", level="WARNING"):
                state = read_state(paths)
            self.assertIsNotNone(state.last_error)
            self.assertEqual(paths.state_file.read_text(), damaged)

    def test_update_output_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            store = StateStore(paths)
            store.update_output("DP-1", path=Path("/wall/a.png"), volume=20)
            self.assertEqual(store.snapshot().outputs["DP-1"].volume, 20)
            self.assertEqual(json.loads(paths.state_file.read_text())["outputs"]["DP-1"]["path"], "/wall/a.png")

    def test_remove_output(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(temporary_paths(directory))
            store.update_output("DP-1")
            self.assertTrue(store.remove_output("DP-1"))
            self.assertFalse(store.remove_output("DP-1"))
            self.assertEqual(store.snapshot().outputs, {})

    def test_set_and_clear_output_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(temporary_paths(directory))
            store.set_output_error("HDMI-A-1", "decoder failed")
            failed = store.snapshot().outputs["HDMI-A-1"]
            self.assertEqual(failed.status, PlaybackStatus.ERROR)
            self.assertEqual(failed.last_error, "decoder failed")
            store.clear_output_error("HDMI-A-1")
            cleared = store.snapshot().outputs["HDMI-A-1"]
            self.assertEqual(cleared.status, PlaybackStatus.STOPPED)
            self.assertIsNone(cleared.last_error)

    def test_mutation_advances_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(temporary_paths(directory))
            before = store.snapshot().updated_at
            store.touch_state()
            self.assertGreaterEqual(store.snapshot().updated_at, before)

    def test_state_permissions_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            write_state(EngineState(), paths)
            self.assertEqual(paths.runtime_home.stat().st_mode & 0o777, 0o700)
            self.assertEqual(paths.state_file.stat().st_mode & 0o777, 0o600)

    def test_read_missing_state_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            state = read_state(paths)
            self.assertEqual(state.outputs, {})
            self.assertFalse(paths.runtime_home.exists())

    def test_constructing_store_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = temporary_paths(directory)
            StateStore(paths)
            self.assertFalse(paths.runtime_home.exists())


if __name__ == "__main__":
    unittest.main()
