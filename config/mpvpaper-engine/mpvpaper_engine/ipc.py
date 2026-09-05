"""Small local JSON Lines protocol for the MPVpaper Engine session service."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import socketserver
import stat
import threading
import time
from typing import Any, Callable

from .paths import EnginePaths


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 2.0


class EngineIPCError(RuntimeError):
    pass


class EngineUnavailableError(EngineIPCError):
    pass


class EngineAlreadyRunningError(EngineIPCError):
    pass


class EngineProtocolError(EngineIPCError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RPCError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _error(request_id, code: str, message: str) -> dict[str, Any]:
    return {
        "id": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }


def _valid_request_id(value: Any) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool)
    ) or (
        isinstance(value, str) and bool(value) and len(value) <= 128
    )


class _RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(MAX_MESSAGE_BYTES + 2)
        if not line:
            return
        if len(line) > MAX_MESSAGE_BYTES:
            self._send(_error(None, "request_too_large", "Request exceeds 64 KiB"))
            return
        if not line.endswith(b"\n"):
            self._send(_error(None, "invalid_json", "Incomplete JSON Lines request"))
            return
        try:
            request = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(_error(None, "invalid_json", "Invalid JSON request"))
            return
        response = self.server.engine_owner.handle_request(request)  # type: ignore[attr-defined]
        self._send(response)

    def _send(self, response: dict[str, Any]) -> None:
        try:
            self.wfile.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass


class _ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(DEFAULT_TIMEOUT)
        return request, address


class EngineServer:
    def __init__(
        self,
        methods: dict[str, Callable[[dict[str, Any]], Any]],
        paths: EnginePaths | None = None,
    ):
        self.paths = paths or EnginePaths.from_environment()
        self.methods = dict(methods)
        self._server: _ThreadingUnixServer | None = None
        self._thread: threading.Thread | None = None
        self._socket_inode: int | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def handle_request(self, request: Any) -> dict[str, Any]:
        if not isinstance(request, dict):
            return _error(None, "invalid_request", "Request must be a JSON object")
        request_id = request.get("id")
        if "id" not in request or not _valid_request_id(request_id):
            return _error(None, "invalid_request", "id must be an integer or non-empty string")
        method = request.get("method")
        if not isinstance(method, str) or not method.strip():
            return _error(request_id, "invalid_request", "method must be a non-empty string")
        params = request.get("params")
        if not isinstance(params, dict):
            return _error(request_id, "invalid_params", "params must be a JSON object")
        handler = self.methods.get(method)
        if handler is None:
            return _error(request_id, "unknown_method", "Unknown method")
        try:
            result = handler(params)
        except RPCError as error:
            return _error(request_id, error.code, str(error))
        except Exception:
            return _error(request_id, "internal_error", "Internal service error")
        return {"id": request_id, "ok": True, "result": result}

    def start(self) -> None:
        if self.running:
            raise EngineAlreadyRunningError("Engine service is already running")
        runtime = self.paths.runtime_home
        runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime.chmod(0o700)
        socket_path = self.paths.engine_socket
        if socket_path.exists() or socket_path.is_socket():
            if not socket_path.is_socket():
                raise EngineIPCError(f"Engine IPC path is not a socket: {socket_path}")
            if self._socket_is_live(socket_path):
                raise EngineAlreadyRunningError(
                    f"Another Engine service is already listening on {socket_path}"
                )
            socket_path.unlink()
        try:
            server = _ThreadingUnixServer(str(socket_path), _RequestHandler)
        except OSError as error:
            raise EngineIPCError(f"Unable to bind Engine socket: {error}") from error
        server.engine_owner = self  # type: ignore[attr-defined]
        socket_path.chmod(0o600)
        self._socket_inode = socket_path.stat().st_ino
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="mpvpaper-engine-ipc",
            daemon=False,
        )
        self._thread.start()

    @staticmethod
    def _socket_is_live(path: Path) -> bool:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.25)
        try:
            probe.connect(str(path))
            return True
        except (ConnectionRefusedError, FileNotFoundError):
            return False
        except socket.timeout:
            return True
        except OSError as error:
            raise EngineIPCError(f"Unable to inspect existing Engine socket: {error}") from error
        finally:
            probe.close()

    def shutdown(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=DEFAULT_TIMEOUT + 1)
        path = self.paths.engine_socket
        try:
            current = path.stat()
            if stat.S_ISSOCK(current.st_mode) and current.st_ino == self._socket_inode:
                path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._socket_inode = None


class EngineClient:
    def __init__(self, paths: EnginePaths | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.paths = paths or EnginePaths.from_environment()
        self.timeout = timeout
        self._next_id = 1

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        payload = json.dumps({
            "id": request_id, "method": method, "params": params or {},
        }, separators=(",", ":")).encode() + b"\n"
        if len(payload) > MAX_MESSAGE_BYTES:
            raise EngineProtocolError("request_too_large", "Request exceeds 64 KiB")
        deadline = time.monotonic() + min(max(self.timeout, 0), 0.75)
        while True:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(self.timeout)
                    client.connect(str(self.paths.engine_socket))
                    client.sendall(payload)
                    response_line = client.makefile("rb").readline(MAX_MESSAGE_BYTES + 2)
                break
            except (FileNotFoundError, ConnectionRefusedError) as error:
                if time.monotonic() >= deadline:
                    raise EngineUnavailableError("Engine service is not running") from error
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            except socket.timeout as error:
                raise TimeoutError("Engine request timed out") from error
            except OSError as error:
                raise EngineUnavailableError(f"Engine connection failed: {error}") from error
        if not response_line or len(response_line) > MAX_MESSAGE_BYTES:
            raise EngineProtocolError("invalid_response", "Invalid Engine response")
        try:
            response = json.loads(response_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EngineProtocolError("invalid_response", "Invalid Engine JSON response") from error
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise EngineProtocolError("invalid_response", "Mismatched Engine response")
        if not response.get("ok"):
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            raise EngineProtocolError(
                str(error.get("code", "request_failed")),
                str(error.get("message", "Engine request failed")),
            )
        return response.get("result")

    def ping(self) -> dict[str, Any]:
        return self.request("ping")

    def get_state(self) -> dict[str, Any]:
        return self.request("get_state")

    def get_output_state(self, output: str) -> dict[str, Any]:
        return self.request("get_output_state", {"output": output})

    def list_outputs(self) -> list[str]:
        return self.request("list_outputs")

    def get_version(self) -> dict[str, Any]:
        return self.request("get_version")

    def play(self, output: str, wallpaper: str) -> dict[str, Any]:
        return self.request("play", {"output": output, "wallpaper": wallpaper})

    def stop(self, output: str) -> dict[str, Any]:
        return self.request("stop", {"output": output})

    def pause(self, output: str) -> dict[str, Any]:
        return self.request("pause", {"output": output})

    def resume(self, output: str) -> dict[str, Any]:
        return self.request("resume", {"output": output})

    def toggle_pause(self, output: str) -> dict[str, Any]:
        return self.request("toggle_pause", {"output": output})

    def restart(self, output: str) -> dict[str, Any]:
        return self.request("restart", {"output": output})

    def seek(self, output: str, seconds: float) -> dict[str, Any]:
        return self.request("seek", {"output": output, "seconds": seconds})

    def seek_relative(self, output: str, delta: float) -> dict[str, Any]:
        return self.request("seek_relative", {"output": output, "delta": delta})

    def set_volume(self, output: str, volume: int) -> dict[str, Any]:
        return self.request("set_volume", {"output": output, "volume": volume})

    def set_mute(self, output: str, muted: bool) -> dict[str, Any]:
        return self.request("set_mute", {"output": output, "muted": muted})

    def set_speed(self, output: str, speed: float) -> dict[str, Any]:
        return self.request("set_speed", {"output": output, "speed": speed})

    def set_loop(self, output: str, enabled: bool) -> dict[str, Any]:
        return self.request("set_loop", {"output": output, "enabled": enabled})

    def set_fit(self, output: str, mode: str) -> dict[str, Any]:
        return self.request("set_fit", {"output": output, "mode": mode})

    def set_color(self, output: str, color: dict[str, Any]) -> dict[str, Any]:
        return self.request("set_color", {"output": output, "color": color})

    def set_performance_profile(self, output: str, profile: str) -> dict[str, Any]:
        return self.request(
            "set_performance_profile", {"output": output, "profile": profile}
        )

    def get_playback_state(self, output: str) -> dict[str, Any]:
        return self.request("get_playback_state", {"output": output})
