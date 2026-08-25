use crate::DeviceRecord;
use serde::Serialize;
use serde_json::Value;
use std::fs::{File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const MAX_DURATION_MS: u64 = 30_000;
const MAX_REPORTS: usize = 1_000;
const MAX_REPORT_BYTES: usize = 4_096;

#[derive(Debug, Serialize)]
struct CapturedReport {
    node: String,
    timestamp_ms: u128,
    report_id: Option<u8>,
    size: usize,
    raw_hex: String,
}

fn number_param(params: Option<&Value>, key: &str, default: u64, maximum: u64) -> u64 {
    params
        .and_then(|value| value.get(key))
        .and_then(Value::as_u64)
        .unwrap_or(default)
        .clamp(1, maximum)
}

fn string_param<'a>(params: Option<&'a Value>, key: &str) -> Option<&'a str> {
    params
        .and_then(|value| value.get(key))
        .and_then(Value::as_str)
}

fn available_nodes(
    device: &DeviceRecord,
    params: Option<&Value>,
    all: bool,
) -> Result<Vec<String>, String> {
    let mut nodes: Vec<_> = device
        .hid_interfaces
        .iter()
        .flat_map(|interface| interface.nodes.iter())
        .chain(device.nodes.iter())
        .filter(|node| node.starts_with("/dev/hidraw"))
        .cloned()
        .collect();
    nodes.sort();
    nodes.dedup();

    if let Some(interface_id) = string_param(params, "interface_id") {
        let Some(interface) = device
            .hid_interfaces
            .iter()
            .find(|interface| interface.id == interface_id)
        else {
            return Err("HID interface not found on this physical device".to_string());
        };
        nodes.retain(|node| interface.nodes.contains(node));
    }
    if let Some(requested) = string_param(params, "node") {
        if !nodes.iter().any(|node| node == requested) {
            return Err("HID node does not belong to this physical device".to_string());
        }
        nodes.retain(|node| node == requested);
    }
    if !all {
        nodes.truncate(1);
    }
    if nodes.is_empty() {
        return Err("device has no readable HID interface".to_string());
    }
    Ok(nodes)
}

fn open_read_only(nodes: Vec<String>) -> Result<Vec<(String, File)>, String> {
    let mut opened = Vec::new();
    let mut errors = Vec::new();
    for node in nodes {
        match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&node)
        {
            Ok(file) => opened.push((node, file)),
            Err(error) => errors.push(format!("{node}: {error}")),
        }
    }
    if opened.is_empty() {
        Err(format!(
            "no HID interface can be opened read-only ({})",
            errors.join("; ")
        ))
    } else {
        Ok(opened)
    }
}

fn descriptor_has_report_ids(device: &DeviceRecord, node: &str) -> bool {
    device
        .hid_interfaces
        .iter()
        .find(|interface| interface.nodes.iter().any(|item| item == node))
        .map(|interface| interface.reports.iter().any(|report| report.id.is_some()))
        .or_else(|| {
            device
                .hid
                .as_ref()
                .map(|descriptor| !descriptor.report_ids.is_empty())
        })
        .unwrap_or(false)
}

fn raw_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub fn capture(device: &DeviceRecord, params: Option<&Value>, all: bool) -> Result<Value, String> {
    let duration_ms = number_param(params, "duration_ms", 1_000, MAX_DURATION_MS);
    let max_reports = number_param(params, "max_reports", 128, MAX_REPORTS as u64) as usize;
    let nodes = available_nodes(device, params, all)?;
    let mut opened = open_read_only(nodes)?;
    let started = Instant::now();
    let duration = Duration::from_millis(duration_ms);
    let mut reports = Vec::new();
    let mut buffer = [0_u8; MAX_REPORT_BYTES];

    while started.elapsed() < duration && reports.len() < max_reports {
        let remaining = duration.saturating_sub(started.elapsed());
        let timeout = remaining.as_millis().min(100) as i32;
        let mut poll_fds: Vec<_> = opened
            .iter()
            .map(|(_, file)| libc::pollfd {
                fd: file.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            })
            .collect();
        // SAFETY: poll_fds points to initialized pollfd values and remains alive for the call.
        let ready = unsafe { libc::poll(poll_fds.as_mut_ptr(), poll_fds.len() as _, timeout) };
        if ready < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(format!("HID poll failed: {error}"));
        }
        if ready == 0 {
            continue;
        }
        for (index, (node, file)) in opened.iter_mut().enumerate() {
            if poll_fds[index].revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0
                && poll_fds[index].revents & libc::POLLIN == 0
            {
                return Err(format!("HID interface disconnected: {node}"));
            }
            if poll_fds[index].revents & libc::POLLIN == 0 {
                continue;
            }
            match file.read(&mut buffer) {
                Ok(0) => {}
                Ok(size) => reports.push(CapturedReport {
                    node: node.clone(),
                    timestamp_ms: SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis(),
                    report_id: descriptor_has_report_ids(device, node).then(|| buffer[0]),
                    size,
                    raw_hex: raw_hex(&buffer[..size]),
                }),
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
                Err(error) => return Err(format!("cannot read {node}: {error}")),
            }
            if reports.len() >= max_reports {
                break;
            }
        }
    }

    Ok(serde_json::json!({
        "reports": reports,
        "duration_ms": started.elapsed().as_millis(),
        "safety": "read-only",
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_limits_are_bounded() {
        let params = serde_json::json!({"duration_ms": 999_999, "max_reports": 999_999});
        assert_eq!(
            number_param(Some(&params), "duration_ms", 1, MAX_DURATION_MS),
            30_000
        );
        assert_eq!(
            number_param(Some(&params), "max_reports", 1, MAX_REPORTS as u64),
            1_000
        );
    }
}
