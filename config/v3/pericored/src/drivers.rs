use crate::{DeviceClass, DeviceRecord};

#[derive(Debug, Clone)]
pub struct Capability {
    pub name: &'static str,
    pub writable: bool,
}

pub trait DeviceDriver: Send + Sync {
    fn name(&self) -> &'static str;
    fn probe(&self, device: &DeviceRecord) -> bool;
    fn capabilities(&self, device: &DeviceRecord) -> Vec<Capability>;
}

pub struct GenericHidDriver;

impl DeviceDriver for GenericHidDriver {
    fn name(&self) -> &'static str {
        "generic-hid"
    }

    fn probe(&self, device: &DeviceRecord) -> bool {
        device.connected
            && !device.nodes.is_empty()
            && matches!(
                device.class,
                DeviceClass::Hid | DeviceClass::Keyboard | DeviceClass::Mouse
            )
    }

    fn capabilities(&self, device: &DeviceRecord) -> Vec<Capability> {
        let mut capabilities = vec![Capability {
            name: "device.info",
            writable: false,
        }];
        if matches!(
            device.class,
            DeviceClass::Hid | DeviceClass::Keyboard | DeviceClass::Mouse
        ) {
            capabilities.push(Capability {
                name: "hid.inspect",
                writable: false,
            });
        }
        capabilities
    }
}

pub struct ReadOnlyDriver;

impl DeviceDriver for ReadOnlyDriver {
    fn name(&self) -> &'static str {
        "read-only"
    }

    fn probe(&self, _device: &DeviceRecord) -> bool {
        true
    }

    fn capabilities(&self, _device: &DeviceRecord) -> Vec<Capability> {
        vec![Capability {
            name: "device.info",
            writable: false,
        }]
    }
}

pub struct DriverRegistry {
    drivers: Vec<Box<dyn DeviceDriver>>,
}

impl Default for DriverRegistry {
    fn default() -> Self {
        Self {
            drivers: vec![Box::new(GenericHidDriver), Box::new(ReadOnlyDriver)],
        }
    }
}

impl DriverRegistry {
    pub fn select(&self, device: &DeviceRecord) -> &dyn DeviceDriver {
        self.drivers
            .iter()
            .find(|driver| driver.probe(device))
            .map(Box::as_ref)
            .expect("read-only driver must always be registered")
    }
}
