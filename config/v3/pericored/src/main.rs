use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use udev::{Device, Enumerator, EventType, MonitorBuilder};

mod drivers;
mod hid;

#[derive(Debug, Serialize, Clone, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum DeviceClass {
    Keyboard,
    Mouse,
    Touchpad,
    Gamepad,
    Monitor,
    Gpu,
    Hid,
    Unknown,
}

#[derive(Debug, Serialize, Clone)]
struct BatteryState {
    percent: Option<u8>,
    charging: Option<bool>,
    low: Option<bool>,
}

#[derive(Debug, Serialize, Clone)]
struct DeviceRecord {
    id: String,
    class: DeviceClass,
    name: String,
    manufacturer: Option<String>,
    vendor_id: Option<String>,
    product_id: Option<String>,
    serial: Option<String>,
    connected: bool,
    nodes: Vec<String>,
    syspath: String,
    connection: String,
    driver: String,
    capabilities: Vec<String>,
    battery: BatteryState,
    #[serde(skip_serializing_if = "Option::is_none")]
    hid: Option<hid::HidDescriptor>,
    #[serde(skip)]
    hid_interfaces: Vec<hid::HidInterface>,
}

#[derive(Default)]
struct DeviceRegistry {
    devices: BTreeMap<String, DeviceRecord>,
    nodes: BTreeMap<String, String>,
    driver_registry: drivers::DriverRegistry,
}

#[derive(Debug, Deserialize)]
struct Request {
    method: String,
    request_id: Option<String>,
    params: Option<serde_json::Value>,
}

type SharedRegistry = Arc<Mutex<DeviceRegistry>>;

fn value(device: &Device, key: &str) -> Option<String> {
    device
        .property_value(key)
        .or_else(|| device.attribute_value(key))
        .map(|value| value.to_string_lossy().into_owned())
        .filter(|value| !value.is_empty())
}

fn inherited_value(device: &Device, key: &str) -> Option<String> {
    let mut current = Some(device.clone());
    while let Some(item) = current {
        if let Some(found) = value(&item, key) {
            return Some(found);
        }
        current = item.parent();
    }
    None
}

fn devnode(device: &Device) -> Option<String> {
    device
        .devnode()
        .map(|path| path.to_string_lossy().into_owned())
}

fn physical_syspath(device: &Device) -> PathBuf {
    if let Some(anchor) = device
        .parent_with_subsystem_devtype("usb", "usb_device")
        .ok()
        .flatten()
        .or_else(|| device.parent_with_subsystem("hid").ok().flatten())
    {
        return anchor.syspath().to_path_buf();
    }
    if device.subsystem().and_then(|value| value.to_str()) == Some("input") {
        for path in device.syspath().ancestors() {
            let is_input_root = path
                .file_name()
                .and_then(|name| name.to_str())
                .and_then(|name| name.strip_prefix("input"))
                .is_some_and(|suffix| {
                    !suffix.is_empty() && suffix.chars().all(|item| item.is_ascii_digit())
                });
            if is_input_root {
                return path.to_path_buf();
            }
        }
    }
    device.syspath().to_path_buf()
}

fn stable_id(device: &Device, vendor: &Option<String>, product: &Option<String>) -> String {
    let anchor = physical_syspath(device);
    let vendor = vendor.as_deref().unwrap_or("unknown");
    let product = product.as_deref().unwrap_or("unknown");
    if let Some(serial) =
        inherited_value(device, "ID_SERIAL_SHORT").or_else(|| inherited_value(device, "serial"))
    {
        return format!("usb:{vendor}:{product}:{serial}");
    }
    format!("sys:{vendor}:{product}:{}", anchor.to_string_lossy())
}

fn classify(device: &Device) -> DeviceClass {
    if inherited_value(device, "ID_INPUT_KEYBOARD").as_deref() == Some("1") {
        return DeviceClass::Keyboard;
    }
    if inherited_value(device, "ID_INPUT_TOUCHPAD").as_deref() == Some("1") {
        return DeviceClass::Touchpad;
    }
    if inherited_value(device, "ID_INPUT_MOUSE").as_deref() == Some("1") {
        return DeviceClass::Mouse;
    }
    if inherited_value(device, "ID_INPUT_JOYSTICK").as_deref() == Some("1")
        || inherited_value(device, "ID_INPUT_GAMEPAD").as_deref() == Some("1")
    {
        return DeviceClass::Gamepad;
    }
    match device.subsystem().and_then(|value| value.to_str()) {
        Some("drm") => DeviceClass::Monitor,
        Some("pci") if value(device, "PCI_CLASS").as_deref() == Some("0x030000") => {
            DeviceClass::Gpu
        }
        Some("hidraw") => DeviceClass::Hid,
        _ => DeviceClass::Unknown,
    }
}

fn connection(device: &Device) -> String {
    inherited_value(device, "ID_BUS")
        .or_else(|| inherited_value(device, "DEVTYPE"))
        .unwrap_or_else(|| "unknown".to_string())
}

fn record_from_device(device: &Device) -> Option<DeviceRecord> {
    let subsystem = device.subsystem().and_then(|value| value.to_str())?;
    if !matches!(subsystem, "input" | "hidraw" | "drm" | "pci") {
        return None;
    }
    let vendor_id =
        inherited_value(device, "ID_VENDOR_ID").or_else(|| inherited_value(device, "idVendor"));
    let product_id =
        inherited_value(device, "ID_MODEL_ID").or_else(|| inherited_value(device, "idProduct"));
    let id = stable_id(device, &vendor_id, &product_id);
    let class = classify(device);
    if subsystem == "pci" && class == DeviceClass::Unknown {
        return None;
    }
    let name = inherited_value(device, "NAME")
        .or_else(|| inherited_value(device, "ID_MODEL_FROM_DATABASE"))
        .or_else(|| inherited_value(device, "ID_MODEL"))
        .unwrap_or_else(|| subsystem.to_string())
        .trim_matches('"')
        .to_string();
    let syspath = physical_syspath(device).to_string_lossy().into_owned();
    let node = devnode(device).unwrap_or_else(|| device.syspath().to_string_lossy().into_owned());
    let hid = if subsystem == "hidraw" {
        hid::read_descriptor(device.syspath())
    } else {
        None
    };
    let hid_interfaces = hid
        .as_ref()
        .map(|descriptor| {
            let candidate = descriptor.usage_pages.iter().any(|page| page.id >= 0xff00);
            let role = if candidate {
                "vendor-defined"
            } else if descriptor
                .collections
                .iter()
                .any(|collection| collection.usage.is_some_and(|usage| usage.page == 0x0d))
            {
                "digitizer"
            } else if descriptor.collections.iter().any(|collection| {
                collection
                    .usage
                    .is_some_and(|usage| usage.page == 0x01 && usage.id == 0x06)
            }) {
                "keyboard"
            } else if descriptor.collections.iter().any(|collection| {
                collection
                    .usage
                    .is_some_and(|usage| usage.page == 0x01 && usage.id == 0x02)
            }) {
                "mouse"
            } else {
                "standard"
            };
            let kernel_name = device
                .parent_with_subsystem("hid")
                .ok()
                .flatten()
                .and_then(|parent| parent.sysname().to_str().map(str::to_string))
                .unwrap_or_else(|| device.sysname().to_string_lossy().into_owned());
            let interface_path = inherited_value(device, "ID_PATH")
                .unwrap_or_else(|| device.syspath().to_string_lossy().into_owned());
            hid::HidInterface {
                id: format!(
                    "path:{}:{}:{interface_path}",
                    vendor_id.as_deref().unwrap_or("unknown"),
                    product_id.as_deref().unwrap_or("unknown")
                ),
                name: kernel_name.clone(),
                kernel_name,
                interface_number: inherited_value(device, "ID_USB_INTERFACE_NUM"),
                vendor_id: vendor_id.clone(),
                product_id: product_id.clone(),
                nodes: vec![node.clone()],
                role: role.to_string(),
                risk: if candidate {
                    "proprietary-candidate".to_string()
                } else {
                    "standard-read-only".to_string()
                },
                candidate,
                descriptor_size: descriptor.size,
                descriptor_sha256: descriptor.descriptor_sha256.clone(),
                usage_pages: descriptor.usage_pages.clone(),
                collections: descriptor.collections.clone(),
                reports: descriptor.reports.clone(),
            }
        })
        .into_iter()
        .collect();
    Some(DeviceRecord {
        id,
        class: class.clone(),
        name,
        manufacturer: inherited_value(device, "ID_VENDOR_FROM_DATABASE")
            .or_else(|| inherited_value(device, "ID_VENDOR")),
        vendor_id,
        product_id,
        serial: inherited_value(device, "ID_SERIAL_SHORT")
            .or_else(|| inherited_value(device, "serial")),
        connected: true,
        nodes: vec![node],
        syspath,
        connection: connection(device),
        driver: String::new(),
        capabilities: Vec::new(),
        battery: BatteryState {
            percent: None,
            charging: None,
            low: None,
        },
        hid,
        hid_interfaces,
    })
}

fn class_priority(class: &DeviceClass) -> u8 {
    match class {
        DeviceClass::Keyboard
        | DeviceClass::Mouse
        | DeviceClass::Touchpad
        | DeviceClass::Gamepad => 3,
        DeviceClass::Monitor | DeviceClass::Gpu => 2,
        DeviceClass::Hid => 1,
        DeviceClass::Unknown => 0,
    }
}

fn useful_name(name: &str) -> bool {
    !matches!(name, "input" | "hidraw" | "drm" | "pci" | "unknown")
}

fn merge_record(existing: &mut DeviceRecord, incoming: DeviceRecord) {
    existing.connected = true;
    if class_priority(&incoming.class) > class_priority(&existing.class) {
        existing.class = incoming.class;
    }
    if useful_name(&incoming.name) && !useful_name(&existing.name) {
        existing.name = incoming.name;
    }
    if existing.manufacturer.is_none() {
        existing.manufacturer = incoming.manufacturer;
    }
    if existing.vendor_id.is_none() {
        existing.vendor_id = incoming.vendor_id;
    }
    if existing.product_id.is_none() {
        existing.product_id = incoming.product_id;
    }
    if existing.serial.is_none() {
        existing.serial = incoming.serial;
    }
    if existing.connection == "unknown" {
        existing.connection = incoming.connection;
    }
    if existing.hid.is_none() {
        existing.hid = incoming.hid;
    }
    for interface in incoming.hid_interfaces {
        if !existing
            .hid_interfaces
            .iter()
            .any(|item| item.id == interface.id)
        {
            existing.hid_interfaces.push(interface);
        }
    }
    for node in incoming.nodes {
        if !existing.nodes.contains(&node) {
            existing.nodes.push(node);
        }
    }
    existing.nodes.sort();
}

impl DeviceRegistry {
    fn add(&mut self, record: DeviceRecord) {
        let id = record.id.clone();
        let mut merged = if let Some(mut existing) = self.devices.remove(&id) {
            merge_record(&mut existing, record);
            existing
        } else {
            record
        };
        let driver = self.driver_registry.select(&merged);
        merged.driver = driver.name().to_string();
        merged.capabilities = driver
            .capabilities(&merged)
            .into_iter()
            .map(|capability| {
                if capability.writable {
                    format!("{}.write", capability.name)
                } else {
                    capability.name.to_string()
                }
            })
            .collect();
        for node in &merged.nodes {
            self.nodes.insert(node.clone(), id.clone());
        }
        self.devices.insert(id, merged);
    }

    fn remove(&mut self, device: &Device) {
        let node =
            devnode(device).unwrap_or_else(|| device.syspath().to_string_lossy().into_owned());
        if let Some(id) = self.nodes.remove(&node) {
            if let Some(record) = self.devices.get_mut(&id) {
                record.nodes.retain(|item| item != &node);
                record.connected = !record.nodes.is_empty();
            }
        }
    }

    fn inventory_json(&self, reason: &str) -> serde_json::Value {
        let devices: Vec<_> = self
            .devices
            .values()
            .filter(|item| item.connected)
            .collect();
        serde_json::json!({
            "event": "inventory",
            "reason": reason,
            "devices": devices,
        })
    }

    fn device(&self, id: &str) -> Option<&DeviceRecord> {
        self.devices.get(id).filter(|device| device.connected)
    }
}

fn socket_path() -> PathBuf {
    env::var_os("PERIPHX_SOCKET")
        .map(PathBuf::from)
        .or_else(|| {
            env::var_os("XDG_RUNTIME_DIR")
                .map(|dir| PathBuf::from(dir).join("periphx/pericored.sock"))
        })
        .unwrap_or_else(|| PathBuf::from("/tmp/periphx-pericored.sock"))
}

fn response(request_id: Option<String>, result: serde_json::Value) -> serde_json::Value {
    serde_json::json!({"ok": true, "request_id": request_id, "result": result, "error": null})
}

fn error_response(request_id: Option<String>, code: &str, message: &str) -> serde_json::Value {
    serde_json::json!({
        "ok": false,
        "request_id": request_id,
        "result": null,
        "error": {"code": code, "message": message}
    })
}

fn handle_request(request: Request, registry: &SharedRegistry) -> serde_json::Value {
    let guard = match registry.lock() {
        Ok(guard) => guard,
        Err(_) => {
            return error_response(
                request.request_id,
                "registry_unavailable",
                "registry unavailable",
            )
        }
    };
    match request.method.as_str() {
        "Ping" | "ping" => response(request.request_id, serde_json::json!({"pong": true})),
        "Version" | "version" => response(
            request.request_id,
            serde_json::json!({"api": "0.2", "daemon": "0.1.0"}),
        ),
        "ListDevices" | "list_devices" | "inventory" => {
            response(request.request_id, guard.inventory_json("ipc"))
        }
        "GetDevice" | "get_device" => {
            let device_id = request
                .params
                .as_ref()
                .and_then(|params| params.get("id"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            match guard.device(device_id) {
                Some(device) => response(request.request_id, serde_json::json!(device)),
                None => error_response(request.request_id, "not_found", "device not found"),
            }
        }
        "GetCapabilities" | "get_capabilities" => response(
            request.request_id,
            serde_json::json!({
                "device_count": guard.devices.values().filter(|device| device.connected).count(),
                "supported": ["ping", "version", "list_devices", "get_device", "get_capabilities", "get_state", "inspect", "get_hid_interfaces", "set_property", "apply_profile"],
                "drivers": ["generic-hid", "generic-input", "read-only"],
            }),
        ),
        "GetState" | "get_state" => {
            let device_id = request
                .params
                .as_ref()
                .and_then(|params| params.get("id"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            match guard.device(device_id) {
                Some(device) => response(
                    request.request_id,
                    serde_json::json!({"connection": device.connection, "battery": device.battery, "capabilities": device.capabilities}),
                ),
                None => error_response(request.request_id, "not_found", "device not found"),
            }
        }
        "GetHidInterfaces" | "get_hid_interfaces" => {
            let device_id = request
                .params
                .as_ref()
                .and_then(|params| params.get("id"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            match guard.device(device_id) {
                Some(device) => response(
                    request.request_id,
                    serde_json::json!({"interfaces": device.hid_interfaces, "safety": "read-only"}),
                ),
                None => error_response(request.request_id, "not_found", "device not found"),
            }
        }
        "Inspect" | "inspect" => {
            let device_id = request
                .params
                .as_ref()
                .and_then(|params| params.get("id"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            match guard.device(device_id) {
                Some(device) => {
                    let usage = device
                        .hid
                        .as_ref()
                        .and_then(|descriptor| descriptor.collections.first())
                        .and_then(|collection| collection.usage);
                    let fingerprint = serde_json::json!({
                        "descriptor_sha256": device.hid.as_ref().map(|item| &item.descriptor_sha256),
                        "interface": device.hid_interfaces.first().and_then(|item| item.interface_number.as_ref()),
                        "pid": device.product_id,
                        "serial": device.serial,
                        "usage": usage.map(|item| format!("0x{:04x}", item.id)),
                        "usage_page": usage.map(|item| format!("0x{:04x}", item.page)),
                        "vid": device.vendor_id,
                    });
                    response(
                        request.request_id,
                        serde_json::json!({
                            "device": device,
                            "hid": {
                                "descriptor": device.hid,
                                "fingerprint": fingerprint,
                                "nodes": device.nodes,
                                "writable_protocol": "unknown",
                            },
                            "safety": "read-only",
                        }),
                    )
                }
                None => error_response(request.request_id, "not_found", "device not found"),
            }
        }
        "SetProperty" | "set_property" | "ApplyProfile" | "apply_profile" => error_response(
            request.request_id,
            "unsupported_capability",
            "no writable driver is registered for this device",
        ),
        _ => error_response(request.request_id, "unknown_method", "unknown method"),
    }
}

fn serve_client(mut stream: UnixStream, registry: SharedRegistry) -> Result<()> {
    let reader = BufReader::new(stream.try_clone()?);
    for line in reader.lines() {
        let line = line?;
        let result = match serde_json::from_str::<Request>(&line) {
            Ok(request) => handle_request(request, &registry),
            Err(error) => error_response(
                None,
                "invalid_request",
                &format!("invalid request: {error}"),
            ),
        };
        writeln!(stream, "{}", serde_json::to_string(&result)?)?;
        stream.flush()?;
    }
    Ok(())
}

fn start_ipc_server(registry: SharedRegistry) -> Result<()> {
    let path = socket_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let _ = fs::remove_file(&path);
    let listener = UnixListener::bind(&path)?;
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    eprintln!("pericored IPC: {}", path.display());
    thread::spawn(move || {
        for stream in listener.incoming() {
            match stream {
                Ok(stream) => {
                    let registry = Arc::clone(&registry);
                    thread::spawn(move || {
                        let _ = serve_client(stream, registry);
                    });
                }
                Err(error) => eprintln!("pericored IPC error: {error}"),
            }
        }
    });
    Ok(())
}

fn initial_scan(registry: &mut DeviceRegistry) -> Result<()> {
    for subsystem in ["input", "hidraw", "drm", "pci"] {
        let mut enumerator = Enumerator::new()?;
        enumerator.match_subsystem(subsystem)?;
        for device in enumerator.scan_devices()? {
            if let Some(record) = record_from_device(&device) {
                registry.add(record);
            }
        }
    }
    Ok(())
}

fn main() -> Result<()> {
    let mut initial_registry = DeviceRegistry::default();
    let monitor = MonitorBuilder::new()?.listen()?;
    initial_scan(&mut initial_registry)?;
    let registry = Arc::new(Mutex::new(initial_registry));
    start_ipc_server(Arc::clone(&registry))?;
    if let Ok(registry) = registry.lock() {
        println!("{}", registry.inventory_json("startup"));
    }

    loop {
        let mut received_event = false;
        for event in monitor.iter() {
            received_event = true;
            let action = event
                .action()
                .and_then(|value| value.to_str())
                .unwrap_or("change");
            match event.event_type() {
                EventType::Add | EventType::Bind | EventType::Change => {
                    if let Some(record) = record_from_device(&event) {
                        if let Ok(mut registry) = registry.lock() {
                            registry.add(record);
                        }
                    }
                }
                EventType::Remove | EventType::Unbind => {
                    if let Ok(mut registry) = registry.lock() {
                        registry.remove(&event);
                    }
                }
                _ => {}
            }
            println!(
                "{}",
                serde_json::json!({
                    "event": "device-change",
                    "action": action,
                    "syspath": event.syspath().to_string_lossy(),
                })
            );
            if let Ok(registry) = registry.lock() {
                println!("{}", registry.inventory_json("udev"));
            }
        }
        if !received_event {
            thread::sleep(Duration::from_millis(100));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record(class: DeviceClass, name: &str, node: &str) -> DeviceRecord {
        DeviceRecord {
            id: "usb:1234:5678:serial".to_string(),
            class,
            name: name.to_string(),
            manufacturer: None,
            vendor_id: Some("1234".to_string()),
            product_id: Some("5678".to_string()),
            serial: Some("serial".to_string()),
            connected: true,
            nodes: vec![node.to_string()],
            syspath: "/sys/test/device".to_string(),
            connection: "usb".to_string(),
            driver: String::new(),
            capabilities: Vec::new(),
            battery: BatteryState {
                percent: None,
                charging: None,
                low: None,
            },
            hid: None,
            hid_interfaces: Vec::new(),
        }
    }

    #[test]
    fn physical_nodes_merge_without_losing_specific_class() {
        let mut registry = DeviceRegistry::default();
        registry.add(record(
            DeviceClass::Keyboard,
            "External Keyboard",
            "/dev/input/event9",
        ));
        registry.add(record(DeviceClass::Hid, "hidraw", "/dev/hidraw4"));

        let device = registry.devices.values().next().unwrap();
        assert_eq!(registry.devices.len(), 1);
        assert_eq!(device.class, DeviceClass::Keyboard);
        assert_eq!(device.name, "External Keyboard");
        assert_eq!(device.driver, "generic-hid");
        assert_eq!(device.nodes, vec!["/dev/hidraw4", "/dev/input/event9"]);
        assert!(device
            .capabilities
            .contains(&"keyboard.buttons".to_string()));
        assert!(!device
            .capabilities
            .iter()
            .any(|item| item.ends_with(".write")));
    }
}
