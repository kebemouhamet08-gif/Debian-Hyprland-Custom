use anyhow::Result;
use serde::Serialize;
use std::collections::BTreeMap;
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

fn value(device: &Device, key: &str) -> Option<String> {
    device
        .property_value(key)
        .or_else(|| device.attribute_value(key))
        .map(|value| value.to_string_lossy().into_owned())
        .filter(|value| !value.is_empty())
}

fn devnode(device: &Device) -> Option<String> {
    device.devnode().map(|path| path.to_string_lossy().into_owned())
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
        let node = devnode(device).unwrap_or_else(|| device.syspath().to_string_lossy().into_owned());
        if let Some(id) = self.nodes.remove(&node) {
            if let Some(record) = self.devices.get_mut(&id) {
                record.connected = false;
                record.nodes.retain(|item| item != &node);
            }
        }
    }

    fn inventory(&self, reason: &str) {
        let devices: Vec<_> = self.devices.values().filter(|item| item.connected).collect();
        println!("{}", serde_json::json!({
            "event": "inventory",
            "reason": reason,
            "devices": devices,
        }));
    }
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
    let mut registry = DeviceRegistry::default();
    let monitor = MonitorBuilder::new()?.listen()?;
    initial_scan(&mut registry)?;
    registry.inventory("startup");

    for event in monitor.iter() {
        let action = event.action().and_then(|value| value.to_str()).unwrap_or("change");
        match event.event_type() {
            EventType::Add | EventType::Bind | EventType::Change => {
                if let Some(record) = record_from_device(&event) {
                    registry.add(record);
                }
            }
            EventType::Remove | EventType::Unbind => registry.remove(&event),
            _ => {}
        }
        println!("{}", serde_json::json!({
            "event": "device-change",
            "action": action,
            "syspath": event.syspath().to_string_lossy(),
        }));
        registry.inventory("udev");
    }
    Ok(())
}
