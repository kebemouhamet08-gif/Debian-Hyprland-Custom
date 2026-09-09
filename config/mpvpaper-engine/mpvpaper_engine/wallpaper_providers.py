"""Ownership handoff from legacy wallpaper providers to MPVpaper."""

from __future__ import annotations

import subprocess
from typing import Callable


PROVIDER_COMMANDS = (
    ("WallpaperAutoChange.sh", ["pkill", "-f", r"(^|/)WallpaperAutoChange[.]sh( |$)"]),
    ("swww-daemon", ["pkill", "-x", "swww-daemon"]),
)


class WallpaperProviderError(RuntimeError):
    pass


class WallpaperProviderManager:
    """Stop known legacy providers through one injectable process boundary."""

    def __init__(self, runner: Callable = subprocess.run):
        self._runner = runner

    def stop_conflicting(self) -> list[str]:
        stopped = []
        for name, command in PROVIDER_COMMANDS:
            try:
                result = self._runner(
                    command, capture_output=True, text=True, timeout=3, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise WallpaperProviderError(
                    f"unable to stop wallpaper provider {name}: {error}"
                ) from error
            # pkill returns 1 when the provider is already absent.
            if result.returncode == 0:
                stopped.append(name)
            elif result.returncode not in (1,):
                message = result.stderr.strip() or f"failed to stop {name}"
                raise WallpaperProviderError(message)
        return stopped
