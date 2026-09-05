#!/usr/bin/env python3

import json
from pathlib import Path

from mpvpaper_engine.ipc import EngineClient, EngineIPCError
from mpvpaper_engine.state import read_state, state_to_dict


def main():
    source = "engine"
    try:
        state = EngineClient(timeout=0.5).get_state()
    except (EngineIPCError, TimeoutError):
        state = state_to_dict(read_state())
        source = "snapshot"
    outputs = state.get("outputs", {})
    playing = [name for name, value in outputs.items()
               if value.get("status") in {"playing", "paused"}]
    paused = bool(playing) and all(outputs[name].get("status") == "paused" for name in playing)
    lines = []
    for name in playing:
        value = outputs[name]
        title = value.get("title") or Path(value.get("path") or "").stem or "—"
        profile = value.get("performance_profile", "auto").upper()
        lines.append(f"{name} · {title} · {value.get('status')} · {profile}")
    payload = {
        "text": "󰸉" + (" 󰏤" if paused else ""),
        "tooltip": "MPVpaper Engine\n" + ("\n".join(lines) if lines else "Aucun wallpaper actif"),
        "class": "paused" if paused else "playing" if playing else "stopped",
        "alt": source,
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
