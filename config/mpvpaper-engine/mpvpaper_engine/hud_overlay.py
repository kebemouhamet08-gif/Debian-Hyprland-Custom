"""Manage a separate transparent desktop HUD process; no wallpaper IPC."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


class DesktopHud:
    def __init__(self, paths, popen=None):
        self.paths = paths
        self.state_file = paths.runtime_home / "desktop-hud.json"
        self.process = None
        self._popen = popen or subprocess.Popen
        self._lock = threading.RLock()
        self._active = False
        self._retry_after = 0.0

    def start(self, settings, previews=None):
        with self._lock:
            self._active = True
            return self.update(settings, previews)

    def update(self, settings, previews=None):
        with self._lock:
            if not self._active:
                return False
            self.paths.runtime_home.mkdir(mode=0o700, parents=True, exist_ok=True)
            payload = {"settings": deepcopy(settings), "previews": deepcopy(previews or {})}
            temporary = self.state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.state_file)
            if self.process is not None and self.process.poll() is None:
                return True
            if time.monotonic() < self._retry_after:
                return False
            self._retry_after = time.monotonic() + 10
            environment = dict(os.environ, GDK_BACKEND="wayland")
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
            self.process = self._popen(
                [sys.executable, "-B", "-m", "mpvpaper_engine.hud_window",
                 str(self.state_file), str(self.paths.config_home), str(os.getpid())],
                env=environment, stdin=subprocess.DEVNULL,
                # Errors go to the engine journal, never a pipe that can fill up.
                stdout=subprocess.DEVNULL,
            )
            return True

    def close(self):
        with self._lock:
            self._active = False
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
                self.process = None
            self.state_file.unlink(missing_ok=True)
