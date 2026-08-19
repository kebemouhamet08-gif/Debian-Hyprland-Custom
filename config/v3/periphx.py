#!/usr/bin/env python3

import argparse
import json
import os
import socket
import sys


def socket_path():
    return os.environ.get(
        "PERIPHX_SOCKET",
        os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "periphx", "pericored.sock"),
    )


def request(method, params=None):
    payload = {"method": method, "params": params or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(socket_path())
        client.sendall((json.dumps(payload) + "\n").encode())
        response = client.makefile("rb").readline()
    if not response:
        raise RuntimeError("pericored n'a pas répondu")
    decoded = json.loads(response)
    if not decoded.get("ok"):
        raise RuntimeError(decoded.get("error", "erreur IPC inconnue"))
    return decoded["result"]


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="periphx", description="Client CLI PeriphX")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="liste les périphériques connectés")
    info = subparsers.add_parser("info", help="affiche un périphérique")
    info.add_argument("device_id")
    subparsers.add_parser("capabilities", help="affiche les capacités du daemon")
    args = parser.parse_args()
    try:
        if args.command == "list":
            print_json(request("ListDevices"))
        elif args.command == "info":
            print_json(request("GetDevice", {"id": args.device_id}))
        else:
            print_json(request("GetCapabilities"))
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"periphx: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
