#!/usr/bin/env python3

import argparse
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path


def socket_path():
    return os.environ.get(
        "PERIPHX_SOCKET",
        os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "periphx", "pericored.sock"),
    )


def request(method, params=None, request_id="cli", timeout=3):
    payload = {"method": method, "request_id": request_id, "params": params or {}}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
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


def print_capture(result):
    reports = result.get("reports") or []
    print(f"PeriphX HID Capture ({len(reports)} reports, lecture seule)")
    for report in reports:
        report_id = report.get("report_id")
        identifier = "none" if report_id is None else f"0x{report_id:02x}"
        print(
            f"{report.get('node', 'unknown')} · {report.get('size', 0)} bytes · "
            f"report {identifier} · {report.get('raw_hex', '')}"
        )


READ_ONLY_DRIVER_CAPABILITIES = {
    "device.info",
    "hid.inspect",
    "hid.report_descriptor",
}


def custom_driver_directory():
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "periphx" / "drivers.d"


def load_driver_manifest(path):
    path = Path(path)
    if path.stat().st_size > 256 * 1024:
        raise ValueError("manifest trop volumineux")
    with path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    allowed = {"schema_version", "name", "version", "match", "capabilities"}
    if not isinstance(manifest, dict) or set(manifest) != allowed:
        raise ValueError("clés de manifest invalides")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("schema_version non pris en charge")
    if not isinstance(manifest["name"], str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{3,64}", manifest["name"]
    ):
        raise ValueError("nom de pilote invalide")
    if not isinstance(manifest["version"], str) or not 0 < len(manifest["version"]) <= 32:
        raise ValueError("version de pilote invalide")
    match = manifest["match"]
    if not isinstance(match, dict) or not set(match).issubset({
        "vendor_id", "product_id", "descriptor_sha256", "interface_number"
    }):
        raise ValueError("bloc match invalide")
    if not {"vendor_id", "product_id"}.issubset(match):
        raise ValueError("VID et PID sont obligatoires")
    for key in ("vendor_id", "product_id"):
        if not isinstance(match[key], str) or not re.fullmatch(
            r"(?:0x)?[0-9A-Fa-f]{4}", match[key]
        ):
            raise ValueError(f"{key} doit contenir quatre chiffres hexadécimaux")
    descriptor_hash = match.get("descriptor_sha256")
    if descriptor_hash is not None and (
        not isinstance(descriptor_hash, str)
        or not re.fullmatch(r"[0-9A-Fa-f]{64}", descriptor_hash)
    ):
        raise ValueError("descriptor_sha256 invalide")
    interface_number = match.get("interface_number")
    if interface_number is not None and (
        not isinstance(interface_number, str)
        or not re.fullmatch(r"[0-9A-Fa-f]{2}", interface_number)
    ):
        raise ValueError("interface_number invalide")
    capabilities = manifest["capabilities"]
    if not isinstance(capabilities, list) or not capabilities or any(
        not isinstance(capability, str)
        or capability not in READ_ONLY_DRIVER_CAPABILITIES
        for capability in capabilities
    ):
        raise ValueError("seules les capacités HID en lecture seule sont autorisées")
    return manifest


def install_driver_manifest(source, update=False):
    manifest = load_driver_manifest(source)
    directory = custom_driver_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    target = directory / f"{manifest['name']}.json"
    if update and not target.exists():
        raise ValueError("pilote absent : utilisez drivers install")
    if not update and target.exists():
        raise ValueError("pilote déjà installé : utilisez drivers update")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, prefix=".driver-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target


def reload_drivers():
    try:
        request("reload_drivers")
        return True
    except (OSError, RuntimeError, json.JSONDecodeError):
        return False


def list_driver_manifests():
    directory = custom_driver_directory()
    result = []
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.json")):
        try:
            manifest = load_driver_manifest(path)
            result.append({
                "name": manifest["name"],
                "version": manifest["version"],
                "path": str(path),
                "valid": True,
            })
        except (OSError, ValueError, json.JSONDecodeError) as error:
            result.append({"path": str(path), "valid": False, "error": str(error)})
    return result


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
    capture = subparsers.add_parser(
        "capture", help="capture des reports HID entrants, sans écriture"
    )
    capture.add_argument("device_id")
    capture.add_argument("--interface", dest="interface_id")
    capture.add_argument("--node")
    capture.add_argument("--duration-ms", type=int, default=1000)
    capture.add_argument("--max-reports", type=int, default=128)
    capture.add_argument("--all", action="store_true", help="écoute toutes les interfaces HID")
    capture.add_argument("--json", action="store_true", help="sortie JSON complète")
    drivers = subparsers.add_parser(
        "drivers", help="gère les manifests de pilotes custom en lecture seule"
    )
    driver_actions = drivers.add_subparsers(dest="driver_action", required=True)
    driver_actions.add_parser("list", help="liste les manifests locaux")
    validate_driver = driver_actions.add_parser("validate", help="valide un manifest")
    validate_driver.add_argument("manifest")
    install_driver = driver_actions.add_parser("install", help="installe un nouveau manifest")
    install_driver.add_argument("manifest")
    update_driver = driver_actions.add_parser("update", help="met à jour un manifest existant")
    update_driver.add_argument("manifest")
    remove_driver = driver_actions.add_parser("remove", help="retire un manifest local")
    remove_driver.add_argument("name")
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
        elif args.command == "capture":
            duration_ms = max(1, min(args.duration_ms, 30_000))
            max_reports = max(1, min(args.max_reports, 1_000))
            params = {
                "id": args.device_id,
                "duration_ms": duration_ms,
                "max_reports": max_reports,
            }
            if args.interface_id:
                params["interface_id"] = args.interface_id
            if args.node:
                params["node"] = args.node
            result = request(
                "monitor_hid_all" if args.all else "monitor_hid",
                params,
                timeout=duration_ms / 1000 + 3,
            )
            if args.json:
                print_json(result)
            else:
                print_capture(result)
        elif args.command == "drivers":
            if args.driver_action == "list":
                print_json(list_driver_manifests())
            elif args.driver_action == "validate":
                manifest = load_driver_manifest(args.manifest)
                print_json({"valid": True, "name": manifest["name"], "safety": "read-only"})
            elif args.driver_action in ("install", "update"):
                target = install_driver_manifest(
                    args.manifest, update=args.driver_action == "update"
                )
                reloaded = reload_drivers()
                print_json({
                    "installed": str(target),
                    "daemon_reloaded": reloaded,
                    "safety": "read-only",
                })
            else:
                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", args.name):
                    raise ValueError("nom de pilote invalide")
                target = custom_driver_directory() / f"{args.name}.json"
                if not target.is_file():
                    raise ValueError("pilote custom introuvable")
                target.unlink()
                print_json({
                    "removed": str(target),
                    "daemon_reloaded": reload_drivers(),
                })
        else:
            print_json(request("get_capabilities"))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"periphx: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
