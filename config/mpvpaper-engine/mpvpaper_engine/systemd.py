"""Small systemd-user abstraction preserving the current transient units."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

from .config import validate_output_name


UNIT_PREFIX = "mpvpaper-engine-wallpaper"
COMMAND_TIMEOUT = 8.0


class SystemdError(RuntimeError):
    pass


def unit_for_output(output: str) -> str:
    if not validate_output_name(output):
        raise ValueError("invalid output name")
    suffix = "all" if output == "*" else re.sub(r"[^A-Za-z0-9_.-]", "-", output)
    return f"{UNIT_PREFIX}-{suffix}.service"


def _default_runner(command, **options):
    return subprocess.run(command, **options)


class SystemdManager:
    def __init__(self, runner: Callable = _default_runner):
        self._runner = runner

    def _run(self, command, *, check=False):
        try:
            result = self._runner(
                command, capture_output=True, text=True,
                timeout=COMMAND_TIMEOUT, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SystemdError(str(error)) from error
        if check and result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "systemd command failed"
            raise SystemdError(message)
        return result

    def start_output(
        self,
        output: str,
        wallpaper: Path,
        mpv_options: str,
        *,
        auto_pause: bool = True,
    ) -> None:
        if not validate_output_name(output):
            raise ValueError("invalid output name")
        wallpaper = Path(wallpaper).expanduser()
        if not wallpaper.is_file():
            raise ValueError(f"wallpaper does not exist: {wallpaper}")
        executable = shutil.which("mpvpaper")
        if executable is None:
            raise SystemdError("mpvpaper is not installed")
        command = [
            "systemd-run", "--user", "--quiet", "--collect",
            f"--unit={unit_for_output(output)}", executable,
        ]
        if auto_pause:
            command.extend(["--auto-pause", "--auto-mode", "full"])
        command.extend(["--mpv-options", mpv_options, output, str(wallpaper)])
        self._run(command, check=True)

    def stop_output(self, output: str) -> None:
        self._run(["systemctl", "--user", "stop", unit_for_output(output)], check=False)

    def restart_output(self, output: str) -> None:
        self._run(["systemctl", "--user", "restart", unit_for_output(output)], check=True)

    def unit_status(self, output: str) -> str:
        result = self._run([
            "systemctl", "--user", "is-active", unit_for_output(output),
        ])
        status = result.stdout.strip()
        if status in {"active", "activating", "deactivating", "failed", "inactive"}:
            return status
        return "unknown"
