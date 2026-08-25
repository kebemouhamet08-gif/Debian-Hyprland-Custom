use crate::{DeviceClass, DeviceRecord};
use std::env;
use std::path::PathBuf;

mod custom;

#[derive(Debug, Clone)]
pub struct Capability {
    pub name: String,
    pub writable: bool,
}

pub trait DeviceDriver: Send + Sync {
    fn name(&self) -> &str;
    fn probe(&self, device: &DeviceRecord) -> bool;
    fn capabilities(&self, device: &DeviceRecord) -> Vec<Capability>;
}

pub struct GenericHidDriver;

impl DeviceDriver for GenericHidDriver {
    fn name(&self) -> &str {
        "generic-hid"
    }

    fn probe(&self, device: &DeviceRecord) -> bool {
        device.connected
            && device
                .nodes
                .iter()
                .any(|node| node.starts_with("/dev/hidraw"))
    }

    fn capabilities(&self, device: &DeviceRecord) -> Vec<Capability> {
        let mut capabilities = vec![Capability {
            name: "device.info".to_string(),
            writable: false,
        }];
        capabilities.push(Capability {
            name: "hid.inspect".to_string(),
            writable: false,
        });
        capabilities.push(Capability {
            name: "hid.report_descriptor".to_string(),
            writable: false,
        });
        add_input_capabilities(&mut capabilities, device);
        capabilities
    }
}

pub struct GenericInputDriver;

impl DeviceDriver for GenericInputDriver {
    fn name(&self) -> &str {
        "generic-input"
    }

    fn probe(&self, device: &DeviceRecord) -> bool {
        device.connected
            && device
                .nodes
                .iter()
                .any(|node| node.starts_with("/dev/input/event"))
    }

    fn capabilities(&self, device: &DeviceRecord) -> Vec<Capability> {
        let mut capabilities = vec![Capability {
            name: "device.info".to_string(),
            writable: false,
        }];
        add_input_capabilities(&mut capabilities, device);
        capabilities
    }
}

fn add_input_capabilities(capabilities: &mut Vec<Capability>, device: &DeviceRecord) {
    for class in &device.classes {
        let name = match class {
            DeviceClass::Keyboard => Some("keyboard.buttons"),
            DeviceClass::Mouse => Some("mouse.buttons"),
            DeviceClass::Touchpad => Some("touchpad.gestures"),
            DeviceClass::Gamepad => Some("gamepad.axes"),
            _ => None,
        };
        if let Some(name) = name {
            capabilities.push(Capability {
                name: name.to_string(),
                writable: false,
            });
        }
    }
}

pub struct ReadOnlyDriver;

impl DeviceDriver for ReadOnlyDriver {
    fn name(&self) -> &str {
        "read-only"
    }

    fn probe(&self, _device: &DeviceRecord) -> bool {
        true
    }

    fn capabilities(&self, _device: &DeviceRecord) -> Vec<Capability> {
        vec![Capability {
            name: "device.info".to_string(),
            writable: false,
        }]
    }
}

pub struct DriverRegistry {
    drivers: Vec<Box<dyn DeviceDriver>>,
}

impl Default for DriverRegistry {
    fn default() -> Self {
        let mut drivers: Vec<Box<dyn DeviceDriver>> = custom_driver_paths()
            .into_iter()
            .flat_map(|directory| custom::load_directory(&directory))
            .map(|driver| Box::new(driver) as Box<dyn DeviceDriver>)
            .collect();
        drivers.push(Box::new(GenericHidDriver));
        drivers.push(Box::new(GenericInputDriver));
        drivers.push(Box::new(ReadOnlyDriver));
        Self { drivers }
    }
}

fn custom_driver_paths() -> Vec<PathBuf> {
    let user_config = env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(|home| PathBuf::from(home).join(".config")))
        .map(|root| root.join("periphx/drivers.d"));
    let mut paths = vec![PathBuf::from("/etc/periphx/drivers.d")];
    if let Some(path) = user_config {
        paths.push(path);
    }
    paths
}

impl DriverRegistry {
    pub fn select(&self, device: &DeviceRecord) -> &dyn DeviceDriver {
        self.drivers
            .iter()
            .find(|driver| driver.probe(device))
            .map(Box::as_ref)
            .expect("read-only driver must always be registered")
    }

    pub fn names(&self) -> Vec<&str> {
        self.drivers.iter().map(|driver| driver.name()).collect()
    }
}
