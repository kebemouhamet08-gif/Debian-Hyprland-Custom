use super::{Capability, DeviceDriver};
use crate::DeviceRecord;
use serde::Deserialize;
use std::fs::{self, File};
use std::io::Read;
use std::path::Path;

const MAX_MANIFEST_BYTES: u64 = 256 * 1024;
const READ_ONLY_CAPABILITIES: &[&str] = &["device.info", "hid.inspect", "hid.report_descriptor"];

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct DriverManifest {
    schema_version: u8,
    name: String,
    version: String,
    #[serde(rename = "match")]
    device_match: DeviceMatch,
    capabilities: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct DeviceMatch {
    vendor_id: String,
    product_id: String,
    descriptor_sha256: Option<String>,
    interface_number: Option<String>,
}

pub struct CustomReadOnlyDriver {
    manifest: DriverManifest,
}

fn normalized_id(value: &str) -> String {
    value.trim().trim_start_matches("0x").to_ascii_lowercase()
}

impl DriverManifest {
    fn validate(&self) -> Result<(), String> {
        if self.schema_version != 1 {
            return Err("unsupported schema_version".to_string());
        }
        if self.name.len() < 3
            || self.name.len() > 64
            || !self
                .name
                .chars()
                .all(|item| item.is_ascii_alphanumeric() || matches!(item, '-' | '_' | '.'))
        {
            return Err("invalid driver name".to_string());
        }
        if self.version.is_empty() || self.version.len() > 32 {
            return Err("invalid driver version".to_string());
        }
        for value in [&self.device_match.vendor_id, &self.device_match.product_id] {
            let value = normalized_id(value);
            if value.len() != 4 || !value.chars().all(|item| item.is_ascii_hexdigit()) {
                return Err("vendor_id and product_id must contain four hex digits".to_string());
            }
        }
        if let Some(hash) = &self.device_match.descriptor_sha256 {
            if hash.len() != 64 || !hash.chars().all(|item| item.is_ascii_hexdigit()) {
                return Err("descriptor_sha256 must contain 64 hex digits".to_string());
            }
        }
        if let Some(interface) = &self.device_match.interface_number {
            if interface.len() != 2 || !interface.chars().all(|item| item.is_ascii_hexdigit()) {
                return Err("interface_number must contain two hex digits".to_string());
            }
        }
        if self.capabilities.is_empty()
            || self
                .capabilities
                .iter()
                .any(|capability| !READ_ONLY_CAPABILITIES.contains(&capability.as_str()))
        {
            return Err("custom manifests may expose read-only capabilities only".to_string());
        }
        Ok(())
    }
}

impl CustomReadOnlyDriver {
    fn from_bytes(bytes: &[u8]) -> Result<Self, String> {
        let manifest: DriverManifest =
            serde_json::from_slice(bytes).map_err(|error| error.to_string())?;
        manifest.validate()?;
        Ok(Self { manifest })
    }
}

impl DeviceDriver for CustomReadOnlyDriver {
    fn name(&self) -> &str {
        &self.manifest.name
    }

    fn probe(&self, device: &DeviceRecord) -> bool {
        let Some(vendor_id) = device.vendor_id.as_deref() else {
            return false;
        };
        let Some(product_id) = device.product_id.as_deref() else {
            return false;
        };
        if normalized_id(vendor_id) != normalized_id(&self.manifest.device_match.vendor_id)
            || normalized_id(product_id) != normalized_id(&self.manifest.device_match.product_id)
        {
            return false;
        }
        if let Some(expected) = &self.manifest.device_match.descriptor_sha256 {
            let actual = device
                .hid
                .as_ref()
                .map(|descriptor| descriptor.descriptor_sha256.as_str());
            if !matches!(actual, Some(actual) if actual.eq_ignore_ascii_case(expected)) {
                return false;
            }
        }
        if let Some(expected) = &self.manifest.device_match.interface_number {
            if !device
                .hid_interfaces
                .iter()
                .any(|interface| interface.interface_number.as_deref() == Some(expected.as_str()))
            {
                return false;
            }
        }
        true
    }

    fn capabilities(&self, _device: &DeviceRecord) -> Vec<Capability> {
        self.manifest
            .capabilities
            .iter()
            .map(|name| Capability {
                name: name.clone(),
                writable: false,
            })
            .collect()
    }
}

pub fn load_directory(path: &Path) -> Vec<CustomReadOnlyDriver> {
    let Ok(entries) = fs::read_dir(path) else {
        return Vec::new();
    };
    let mut paths: Vec<_> = entries
        .flatten()
        .filter(|entry| entry.file_type().is_ok_and(|kind| kind.is_file()))
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("json"))
        .collect();
    paths.sort();
    paths
        .into_iter()
        .filter_map(|path| {
            let file = File::open(&path).ok()?;
            if file.metadata().ok()?.len() > MAX_MANIFEST_BYTES {
                eprintln!("PeriphX ignored oversized custom driver {}", path.display());
                return None;
            }
            let mut bytes = Vec::new();
            file.take(MAX_MANIFEST_BYTES).read_to_end(&mut bytes).ok()?;
            match CustomReadOnlyDriver::from_bytes(&bytes) {
                Ok(driver) => Some(driver),
                Err(error) => {
                    eprintln!("PeriphX ignored custom driver {}: {error}", path.display());
                    None
                }
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_writable_or_weak_manifests() {
        let writable = br#"{
            "schema_version": 1,
            "name": "unsafe-driver",
            "version": "1.0.0",
            "match": {"vendor_id": "1234", "product_id": "5678"},
            "capabilities": ["mouse.dpi.write"]
        }"#;
        assert!(CustomReadOnlyDriver::from_bytes(writable).is_err());

        let weak = br#"{
            "schema_version": 1,
            "name": "weak-driver",
            "version": "1.0.0",
            "match": {"vendor_id": "*", "product_id": "*"},
            "capabilities": ["device.info"]
        }"#;
        assert!(CustomReadOnlyDriver::from_bytes(weak).is_err());
    }

    #[test]
    fn accepts_strict_read_only_manifest() {
        let manifest = br#"{
            "schema_version": 1,
            "name": "example-mouse",
            "version": "1.2.0",
            "match": {
                "vendor_id": "1234",
                "product_id": "5678",
                "descriptor_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            },
            "capabilities": ["device.info", "hid.inspect"]
        }"#;
        assert!(CustomReadOnlyDriver::from_bytes(manifest).is_ok());
    }
}
