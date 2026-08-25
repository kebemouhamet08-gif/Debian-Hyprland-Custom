use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HidUsagePage {
    pub id: u16,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HidCollection {
    pub kind: u8,
    pub usage: Option<HidUsage>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct HidUsage {
    pub page: u16,
    pub id: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HidReport {
    #[serde(rename = "type")]
    pub report_type: &'static str,
    pub id: Option<u8>,
    pub size_bits: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HidDescriptor {
    pub size: usize,
    pub descriptor_sha256: String,
    pub raw_hex: String,
    pub usage_pages: Vec<HidUsagePage>,
    pub collections: Vec<HidCollection>,
    pub report_ids: Vec<u8>,
    pub reports: Vec<HidReport>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HidInterface {
    pub id: String,
    pub name: String,
    pub kernel_name: String,
    pub interface_number: Option<String>,
    pub vendor_id: Option<String>,
    pub product_id: Option<String>,
    pub nodes: Vec<String>,
    pub role: String,
    pub risk: String,
    pub candidate: bool,
    pub descriptor_size: usize,
    pub descriptor_sha256: String,
    pub usage_pages: Vec<HidUsagePage>,
    pub collections: Vec<HidCollection>,
    pub reports: Vec<HidReport>,
}

#[derive(Clone, Copy, Default)]
struct GlobalState {
    usage_page: Option<u16>,
    report_size: u32,
    report_count: u32,
    report_id: Option<u8>,
}

fn unsigned(data: &[u8]) -> u32 {
    data.iter().enumerate().fold(0, |value, (shift, byte)| {
        value | ((*byte as u32) << (shift * 8))
    })
}

fn usage_page_name(id: u16) -> String {
    match id {
        0x01 => "Generic Desktop",
        0x07 => "Keyboard/Keypad",
        0x08 => "LED",
        0x09 => "Button",
        0x0c => "Consumer",
        0x0d => "Digitizer",
        0x0f => "Physical Interface",
        0x20 => "Sensors",
        0x84 => "Power Device",
        0x85 => "Battery System",
        0xff00..=0xffff => return format!("Vendor Defined 0x{id:04X}"),
        _ => "Unknown",
    }
    .to_string()
}

pub fn parse_descriptor(bytes: &[u8]) -> HidDescriptor {
    let mut offset = 0;
    let mut state = GlobalState::default();
    let mut stack = Vec::new();
    let mut local_usage = None;
    let mut usage_pages = BTreeSet::new();
    let mut collections = Vec::new();
    let mut report_ids = BTreeSet::new();
    let mut reports: BTreeMap<(&'static str, Option<u8>), u32> = BTreeMap::new();

    while offset < bytes.len() {
        let prefix = bytes[offset];
        offset += 1;
        if prefix == 0xfe {
            if offset + 2 > bytes.len() {
                break;
            }
            let length = bytes[offset] as usize;
            offset += 2;
            if offset + length > bytes.len() {
                break;
            }
            offset += length;
            continue;
        }

        let size = match prefix & 0x03 {
            3 => 4,
            value => value as usize,
        };
        if offset + size > bytes.len() {
            break;
        }
        let data = &bytes[offset..offset + size];
        offset += size;
        let value = unsigned(data);
        let item_type = (prefix >> 2) & 0x03;
        let tag = (prefix >> 4) & 0x0f;

        match (item_type, tag) {
            (1, 0) => {
                state.usage_page = Some(value as u16);
                usage_pages.insert(value as u16);
            }
            (1, 7) => state.report_size = value,
            (1, 8) => {
                state.report_id = Some(value as u8);
                report_ids.insert(value as u8);
            }
            (1, 9) => state.report_count = value,
            (1, 10) => stack.push(state),
            (1, 11) => {
                if let Some(previous) = stack.pop() {
                    state = previous;
                }
            }
            (2, 0) => {
                if size > 2 {
                    usage_pages.insert((value >> 16) as u16);
                    local_usage = Some(HidUsage {
                        page: (value >> 16) as u16,
                        id: value as u16,
                    });
                } else {
                    local_usage = state.usage_page.map(|page| HidUsage {
                        page,
                        id: value as u16,
                    });
                }
            }
            (0, 10) => {
                collections.push(HidCollection {
                    kind: value as u8,
                    usage: local_usage,
                });
                local_usage = None;
            }
            (0, 8) | (0, 9) | (0, 11) => {
                let report_type = match tag {
                    8 => "input",
                    9 => "output",
                    _ => "feature",
                };
                let bits = state.report_size.saturating_mul(state.report_count);
                let entry = reports.entry((report_type, state.report_id)).or_default();
                *entry = entry.saturating_add(bits);
                local_usage = None;
            }
            (0, 12) => local_usage = None,
            _ => {}
        }
    }

    HidDescriptor {
        size: bytes.len(),
        descriptor_sha256: format!("{:x}", Sha256::digest(bytes)),
        raw_hex: bytes.iter().map(|byte| format!("{byte:02x}")).collect(),
        usage_pages: usage_pages
            .into_iter()
            .map(|id| HidUsagePage {
                id,
                name: usage_page_name(id),
            })
            .collect(),
        collections,
        report_ids: report_ids.into_iter().collect(),
        reports: reports
            .into_iter()
            .map(|((report_type, report_id), bits)| HidReport {
                report_type,
                id: report_id,
                size_bits: bits,
            })
            .collect(),
    }
}

pub fn read_descriptor(syspath: &Path) -> Option<HidDescriptor> {
    let mut current = Some(syspath.to_path_buf());
    while let Some(path) = current {
        let candidate: PathBuf = path.join("report_descriptor");
        if let Ok(file) = File::open(candidate) {
            let mut bytes = Vec::new();
            if file.take(1024 * 1024).read_to_end(&mut bytes).is_ok() && !bytes.is_empty() {
                return Some(parse_descriptor(&bytes));
            }
        }
        current = path.parent().map(Path::to_path_buf);
        if current.as_deref() == Some(Path::new("/")) {
            break;
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_aggregates_keyboard_reports() {
        let descriptor = parse_descriptor(&[
            0x05, 0x01, 0x09, 0x06, 0xa1, 0x01, 0x05, 0x07, 0x75, 0x01, 0x95, 0x08, 0x81, 0x02,
            0x75, 0x08, 0x95, 0x06, 0x81, 0x00, 0xc0,
        ]);
        assert_eq!(descriptor.size, 21);
        assert_eq!(descriptor.collections.len(), 1);
        assert_eq!(
            descriptor.collections[0].usage,
            Some(HidUsage { page: 1, id: 6 })
        );
        assert_eq!(descriptor.reports.len(), 1);
        assert_eq!(descriptor.reports[0].id, None);
        assert_eq!(descriptor.reports[0].size_bits, 56);
    }

    #[test]
    fn keeps_report_ids_and_types_separate() {
        let descriptor = parse_descriptor(&[
            0x85, 0x02, 0x75, 0x08, 0x95, 0x02, 0x81, 0x00, 0x91, 0x00, 0x85, 0x03, 0x95, 0x01,
            0xb1, 0x00,
        ]);
        assert_eq!(descriptor.report_ids, vec![2, 3]);
        assert_eq!(descriptor.reports.len(), 3);
        assert!(descriptor.reports.iter().any(|report| {
            report.report_type == "input" && report.id == Some(2) && report.size_bits == 16
        }));
    }

    #[test]
    fn truncated_and_long_items_never_panic() {
        for bytes in [
            vec![0x75],
            vec![0xfe],
            vec![0xfe, 4, 1, 2],
            vec![0xff, 1, 2],
        ] {
            let descriptor = parse_descriptor(&bytes);
            assert_eq!(descriptor.size, bytes.len());
        }
    }

    #[test]
    fn global_push_and_pop_restore_report_shape() {
        let descriptor = parse_descriptor(&[
            0x75, 0x08, 0x95, 0x01, 0xa4, 0x75, 0x01, 0x95, 0x02, 0x81, 0x00, 0xb4, 0x81, 0x00,
        ]);
        assert_eq!(descriptor.reports[0].size_bits, 10);
    }

    #[test]
    fn exposes_compatible_raw_hex_and_sha256() {
        let descriptor = parse_descriptor(b"abc");
        assert_eq!(descriptor.raw_hex, "616263");
        assert_eq!(
            descriptor.descriptor_sha256,
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
