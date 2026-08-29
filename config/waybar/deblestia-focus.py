#!/usr/bin/env python3

"""Petit minuteur Focus persistant pour Deblestia Nova."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path


STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "deblestia"
STATE_FILE = STATE_DIR / "focus.json"
LOCK_FILE = STATE_DIR / "focus.lock"
DURATIONS = {
    "focus": max(1, int(os.environ.get("DEBLESTIA_FOCUS_MINUTES", "25"))) * 60,
    "break": max(1, int(os.environ.get("DEBLESTIA_BREAK_MINUTES", "5"))) * 60,
    "long_break": max(1, int(os.environ.get("DEBLESTIA_LONG_BREAK_MINUTES", "15"))) * 60,
}
LABELS = {"focus": "Concentration", "break": "Pause", "long_break": "Pause longue"}
ICONS = {"focus": "󰔛", "break": "󰏤", "long_break": "󰗽"}


def default_state() -> dict[str, object]:
    return {
        "phase": "focus",
        "running": False,
        "remaining": DURATIONS["focus"],
        "started_at": int(time.time()),
        "cycle": 0,
    }


def load_state() -> dict[str, object]:
    try:
        state = json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default_state()
    phase = state.get("phase")
    if phase not in DURATIONS:
        return default_state()
    try:
        return {
            "phase": phase,
            "running": bool(state.get("running", False)),
            "remaining": max(0, int(state.get("remaining", DURATIONS[phase]))),
            "started_at": int(state.get("started_at", time.time())),
            "cycle": max(0, int(state.get("cycle", 0))),
        }
    except (TypeError, ValueError):
        return default_state()


def save_state(state: dict[str, object]) -> None:
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, separators=(",", ":")) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(STATE_FILE)


def seconds_left(state: dict[str, object], now: int) -> int:
    remaining = int(state["remaining"])
    if state["running"]:
        remaining -= max(0, now - int(state["started_at"]))
    return max(0, remaining)


def next_phase(state: dict[str, object], now: int) -> None:
    phase = str(state["phase"])
    cycle = int(state["cycle"])
    if phase == "focus":
        cycle += 1
        phase = "long_break" if cycle % 4 == 0 else "break"
    else:
        phase = "focus"
    state.update(phase=phase, cycle=cycle, remaining=DURATIONS[phase], started_at=now)


def notify_phase(state: dict[str, object]) -> None:
    if not shutil_which("notify-send"):
        return
    phase = str(state["phase"])
    minutes = DURATIONS[phase] // 60
    subprocess.Popen(
        ["notify-send", "Deblestia Focus", f"{LABELS[phase]} · {minutes} min"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def shutil_which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def refresh(state: dict[str, object], now: int) -> None:
    if state["running"] and seconds_left(state, now) == 0:
        next_phase(state, now)
        notify_phase(state)


def render(state: dict[str, object], now: int) -> None:
    phase = str(state["phase"])
    remaining = seconds_left(state, now)
    minutes, seconds = divmod(remaining, 60)
    status = "actif" if state["running"] else "en pause"
    compact = os.environ.get("DEBLESTIA_FOCUS_COMPACT") == "1"
    output = {
        "text": ICONS[phase] if compact else f"{ICONS[phase]} {minutes:02d}:{seconds:02d}",
        "tooltip": (
            f"{LABELS[phase]} · {status} · cycle {int(state['cycle']) % 4 + 1}/4\n"
            "Clic : démarrer/pause · Milieu : étape suivante · Droit : réinitialiser"
        ),
        "class": ["focus", phase, "running" if state["running"] else "paused"],
        "percentage": round(remaining * 100 / DURATIONS[phase]),
    }
    print(json.dumps(output, ensure_ascii=False))


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        now = int(time.time())
        refresh(state, now)

        if action == "toggle":
            state["remaining"] = seconds_left(state, now)
            state["running"] = not bool(state["running"])
            state["started_at"] = now
        elif action == "reset":
            state = default_state()
        elif action == "skip":
            running = bool(state["running"])
            next_phase(state, now)
            state["running"] = running
            notify_phase(state)
        elif action != "status":
            raise SystemExit(f"Action inconnue : {action}")

        save_state(state)
        render(state, now)


if __name__ == "__main__":
    main()
