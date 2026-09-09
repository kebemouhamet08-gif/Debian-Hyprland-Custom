"""Preview session isolated from the real wallpaper playback."""

from __future__ import annotations

import ctypes.util
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from typing import Callable

from .metadata import MEDIA_EXTENSIONS
from .paths import EnginePaths
from .playback import MpvClient, PlaybackError


PREVIEW_START_TIMEOUT = 2.0


@dataclass(frozen=True, slots=True)
class PreviewCapabilities:
    libmpv: str | None
    mpv_executable: str | None
    recommended: str
    libmpv_status: str = "experimental-unvalidated-gtk-wayland"


def probe_preview_backends(
    find_library: Callable = ctypes.util.find_library,
    which: Callable = shutil.which,
) -> PreviewCapabilities:
    library = find_library("mpv")
    executable = which("mpv")
    # GTK4/Wayland embedding must be validated separately before libmpv is selected.
    recommended = "subprocess" if executable else "static"
    return PreviewCapabilities(library, executable, recommended)


class PreviewSession:
    def __init__(
        self,
        paths: EnginePaths | None = None,
        *,
        popen: Callable = subprocess.Popen,
        capabilities: PreviewCapabilities | None = None,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.popen = popen
        self.capabilities = capabilities or probe_preview_backends()
        self.process = None
        self.socket_path: Path | None = None
        self.path: Path | None = None
        self.backend = "static"

    def start(self, path: Path, *, window_id: int | None = None) -> str:
        self.close()
        path = Path(path).expanduser().resolve()
        if not path.is_file() or path.suffix.casefold() not in MEDIA_EXTENSIONS:
            raise ValueError("preview media is missing or unsupported")
        self.path = path
        if self.capabilities.recommended != "subprocess" or not self.capabilities.mpv_executable:
            self.backend = "static"
            return self.backend
        self.paths.runtime_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.socket_path = self.paths.runtime_home / f"preview-{uuid.uuid4().hex}.sock"
        command = [
            self.capabilities.mpv_executable,
            "--no-config", "--idle=yes", "--keep-open=yes", "--loop-file=inf",
            "--mute=yes", f"--input-ipc-server={self.socket_path}",
        ]
        if window_id is not None:
            command.append(f"--wid={int(window_id)}")
        else:
            command.append("--force-window=immediate")
        command.append(str(path))
        try:
            self.process = self.popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            self.process = None
            self.backend = "static"
            return self.backend
        deadline = time.monotonic() + PREVIEW_START_TIMEOUT
        while time.monotonic() < deadline:
            if self.socket_path.is_socket():
                self.backend = "subprocess"
                return self.backend
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        self.close()
        self.path = path
        self.backend = "static"
        return self.backend

    def _client(self) -> MpvClient:
        if self.backend != "subprocess" or self.socket_path is None:
            raise PlaybackError("interactive preview is unavailable")
        return MpvClient(self.socket_path, timeout=1.0)

    def play(self) -> None:
        self._client().set_property("pause", False)

    def pause(self) -> None:
        self._client().set_property("pause", True)

    def seek(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("preview position cannot be negative")
        self._client().seek(float(seconds), "absolute")

    def mute(self, muted: bool = True) -> None:
        if not isinstance(muted, bool):
            raise ValueError("muted must be boolean")
        self._client().set_property("mute", muted)

    def restart(self) -> None:
        client = self._client()
        client.seek(0.0, "absolute")
        client.set_property("pause", False)

    def close(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        if self.socket_path is not None:
            try:
                self.socket_path.unlink()
            except FileNotFoundError:
                pass
        self.socket_path = None
        self.backend = "static"
