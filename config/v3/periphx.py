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


def usage_page_names(descriptor):
    names = []
    for page in (descriptor or {}).get("usage_pages", []):
        if isinstance(page, dict):
            names.append(page.get("name") or f"0x{page.get('id', 0):04x}")
        else:
            names.append(str(page))
    return names


def print_inspection(result):
    device = result.get("device") or {}
    hid = result.get("hid") or {}
    descriptor = hid.get("descriptor") or device.get("hid") or hid
    nodes = hid.get("nodes") or device.get("nodes") or []
    usage_pages = usage_page_names(descriptor)
    print("PeriphX Device Inspector")
    print(f"\nDevice\n  {device.get('name') or 'unknown'}")
    print(f"\nUSB\n  VID: {device.get('vendor_id') or 'unknown'}")
    print(f"  PID: {device.get('product_id') or 'unknown'}")
    print(f"\nHID\n  Nodes: {', '.join(nodes) or 'none'}")
    print(f"  Usage pages: {', '.join(usage_pages) or 'unknown'}")
    print(f"\nDriver\n  {device.get('driver') or 'unknown'}")
    print(f"  Writable protocol: {hid.get('writable_protocol') or 'unknown'}")


def print_interfaces(result):
    interfaces = result.get("interfaces") or []
    print(f"PeriphX HID Interfaces ({len(interfaces)})")
    for interface in interfaces:
        print(f"\n{interface.get('name') or interface.get('id') or 'unknown'}")
        print(f"  ID: {interface.get('id') or 'unknown'}")
        print(f"  Role: {interface.get('role') or 'unknown'}")
        print(f"  Risk: {interface.get('risk') or 'unknown'}")
        print(f"  Nodes: {', '.join(interface.get('nodes') or []) or 'none'}")
        print(f"  Descriptor: {interface.get('descriptor_size', 0)} bytes")


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
    interfaces = subparsers.add_parser(
        "interfaces", help="liste les interfaces HID physiques en lecture seule"
    )
    interfaces.add_argument("device_id")
    interfaces.add_argument("--json", action="store_true", help="sortie JSON complète")
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
                print_inspection(result)
        elif args.command == "interfaces":
            result = request("get_hid_interfaces", {"id": args.device_id})
            if args.json:
                print_json(result)
            else:
                print_interfaces(result)
        else:
            print_json(request("get_capabilities"))
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"periphx: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
