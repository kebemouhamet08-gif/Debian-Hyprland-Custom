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
use udev::{Device, Enumerator, EventType, MonitorBuilder};

#[derive(Debug, Serialize, Clone)]
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
}

#[derive(Default)]
struct DeviceRegistry {
    devices: BTreeMap<String, DeviceRecord>,
    nodes: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct Request {
    method: String,
    id: Option<String>,
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

fn devnode(device: &Device) -> Option<String> {
    device
        .devnode()
        .map(|path| path.to_string_lossy().into_owned())
}

fn stable_id(device: &Device, vendor: &Option<String>, product: &Option<String>) -> String {
    let vendor = vendor.as_deref().unwrap_or("unknown");
    let product = product.as_deref().unwrap_or("unknown");
    if let Some(serial) = value(device, "ID_SERIAL_SHORT").or_else(|| value(device, "serial")) {
        return format!("usb:{vendor}:{product}:{serial}");
    }
    if let Some(path) = value(device, "ID_PATH") {
        return format!("path:{vendor}:{product}:{path}");
    }
    format!("sys:{}", device.syspath().to_string_lossy())
}

fn classify(device: &Device) -> DeviceClass {
    if value(device, "ID_INPUT_KEYBOARD").as_deref() == Some("1") {
        return DeviceClass::Keyboard;
    }
    if value(device, "ID_INPUT_TOUCHPAD").as_deref() == Some("1") {
        return DeviceClass::Touchpad;
    }
    if value(device, "ID_INPUT_MOUSE").as_deref() == Some("1") {
        return DeviceClass::Mouse;
    }
    if value(device, "ID_INPUT_JOYSTICK").as_deref() == Some("1")
        || value(device, "ID_INPUT_GAMEPAD").as_deref() == Some("1")
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

fn record_from_device(device: &Device) -> Option<DeviceRecord> {
    let subsystem = device.subsystem().and_then(|value| value.to_str())?;
    if !matches!(subsystem, "input" | "hidraw" | "drm" | "pci") {
        return None;
    }
    let vendor_id = value(device, "ID_VENDOR_ID").or_else(|| value(device, "idVendor"));
    let product_id = value(device, "ID_MODEL_ID").or_else(|| value(device, "idProduct"));
    let id = stable_id(device, &vendor_id, &product_id);
    let name = value(device, "NAME")
        .or_else(|| value(device, "ID_MODEL_FROM_DATABASE"))
        .or_else(|| value(device, "ID_MODEL"))
        .unwrap_or_else(|| subsystem.to_string());
    let syspath = device.syspath().to_string_lossy().into_owned();
    let node = devnode(device).unwrap_or_else(|| syspath.clone());
    Some(DeviceRecord {
        id,
        class: classify(device),
        name,
        manufacturer: value(device, "ID_VENDOR_FROM_DATABASE")
            .or_else(|| value(device, "ID_VENDOR")),
        vendor_id,
        product_id,
        serial: value(device, "ID_SERIAL_SHORT").or_else(|| value(device, "serial")),
        connected: true,
        nodes: vec![node],
        syspath,
    })
}

impl DeviceRegistry {
    fn add(&mut self, record: DeviceRecord) {
        let id = record.id.clone();
        for node in &record.nodes {
            self.nodes.insert(node.clone(), id.clone());
        }
        if let Some(existing) = self.devices.get_mut(&id) {
            existing.connected = true;
            existing.class = record.class;
            existing.name = record.name;
            for node in record.nodes {
                if !existing.nodes.contains(&node) {
                    existing.nodes.push(node);
                }
            }
        } else {
            self.devices.insert(id, record);
        }
    }

    fn remove(&mut self, device: &Device) {
        let node =
            devnode(device).unwrap_or_else(|| device.syspath().to_string_lossy().into_owned());
        if let Some(id) = self.nodes.remove(&node) {
            if let Some(record) = self.devices.get_mut(&id) {
                record.connected = false;
                record.nodes.retain(|item| item != &node);
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

fn response(id: Option<String>, result: serde_json::Value) -> serde_json::Value {
    serde_json::json!({"id": id, "ok": true, "result": result})
}

fn error_response(id: Option<String>, message: &str) -> serde_json::Value {
    serde_json::json!({"id": id, "ok": false, "error": message})
}

fn handle_request(request: Request, registry: &SharedRegistry) -> serde_json::Value {
    let guard = match registry.lock() {
        Ok(guard) => guard,
        Err(_) => return error_response(request.id, "registry unavailable"),
    };
    match request.method.as_str() {
        "ListDevices" | "inventory" => response(request.id, guard.inventory_json("ipc")),
        "GetDevice" => {
            let device_id = request
                .params
                .as_ref()
                .and_then(|params| params.get("id"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            match guard.device(device_id) {
                Some(device) => response(request.id, serde_json::json!(device)),
                None => error_response(request.id, "device not found"),
            }
        }
        "GetCapabilities" => response(
            request.id,
            serde_json::json!({
                "device_count": guard.devices.values().filter(|device| device.connected).count(),
                "supported": ["inventory", "device-details", "hotplug-events"],
            }),
        ),
        "GetBattery" | "GetConnection" | "GetProfile" => response(
            request.id,
            serde_json::json!({
                "status": "not-implemented",
                "message": "backend not available for this device",
            }),
        ),
        _ => error_response(request.id, "unknown method"),
    }
}

fn serve_client(mut stream: UnixStream, registry: SharedRegistry) -> Result<()> {
    let reader = BufReader::new(stream.try_clone()?);
    for line in reader.lines() {
        let line = line?;
        let result = match serde_json::from_str::<Request>(&line) {
            Ok(request) => handle_request(request, &registry),
            Err(error) => error_response(None, &format!("invalid request: {error}")),
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

    for event in monitor.iter() {
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
    Ok(())
}
