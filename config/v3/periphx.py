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


def request(method, params=None, request_id="cli"):
    payload = {"method": method, "request_id": request_id, "params": params or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(socket_path())
        client.sendall((json.dumps(payload) + "\n").encode())
        response = client.makefile("rb").readline()
    if not response:
        raise RuntimeError("pericored n'a pas répondu")
    decoded = json.loads(response)
    if not decoded.get("ok"):
        error = decoded.get("error") or {}
        raise RuntimeError(error.get("message", "erreur IPC inconnue"))
    return decoded["result"]


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="periphx", description="Client CLI PeriphX")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="liste les périphériques connectés")
    subparsers.add_parser("ping", help="vérifie que pericored répond")
    subparsers.add_parser("version", help="affiche les versions API et daemon")
    info = subparsers.add_parser("info", help="affiche un périphérique")
    info.add_argument("device_id")
    inspect = subparsers.add_parser("inspect", help="inspecte un périphérique HID")
    inspect.add_argument("device_id")
    inspect.add_argument("--json", action="store_true", help="sortie JSON complète")
    subparsers.add_parser("capabilities", help="affiche les capacités du daemon")
    args = parser.parse_args()
    try:
        if args.command == "list":
            print_json(request("list_devices"))
        elif args.command == "ping":
            print_json(request("ping"))
        elif args.command == "version":
            print_json(request("version"))
        elif args.command == "info":
            print_json(request("get_device", {"id": args.device_id}))
        elif args.command == "inspect":
            result = request("inspect", {"id": args.device_id})
            if args.json:
                print_json(result)
            else:
                device = result["device"]
                hid = result["hid"]
                print("PeriphX Device Inspector")
                print(f"\nDevice\n  {device['name']}")
                print(f"\nUSB\n  VID: {device.get('vendor_id') or 'unknown'}")
                print(f"  PID: {device.get('product_id') or 'unknown'}")
                print(f"\nHID\n  Nodes: {', '.join(hid['nodes']) or 'none'}")
                print(f"  Usage pages: {', '.join(hid['usage_pages']) or 'unknown'}")
                print(f"\nDriver\n  {device['driver']}")
                print(f"  Writable protocol: {hid['writable_protocol']}")
        else:
            print_json(request("get_capabilities"))
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"periphx: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
