use crate::{DeviceClass, DeviceRecord};
use serde::Serialize;
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::mem::size_of;
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

const EV_KEY: u16 = 0x01;
const EV_REL: u16 = 0x02;
const EV_ABS: u16 = 0x03;

#[repr(C)]
#[derive(Clone, Copy)]
struct RawInputEvent {
    time: libc::timeval,
    event_type: u16,
    code: u16,
    value: i32,
}

#[repr(C)]
#[derive(Default)]
struct InputAbsInfo {
    value: i32,
    minimum: i32,
    maximum: i32,
    fuzz: i32,
    flat: i32,
    resolution: i32,
}

#[derive(Debug, Serialize)]
pub struct InputControl {
    control: String,
    kind: &'static str,
    code: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    minimum: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    maximum: Option<i32>,
}

fn event_nodes(device: &DeviceRecord) -> Vec<String> {
    device
        .nodes
        .iter()
        .filter(|node| node.starts_with("/dev/input/event"))
        .cloned()
        .collect()
}

fn key_name(code: u16) -> String {
    match code {
        1 => "escape".into(),
        14 => "backspace".into(),
        15 => "tab".into(),
        28 => "enter".into(),
        29 => "left_ctrl".into(),
        42 => "left_shift".into(),
        54 => "right_shift".into(),
        56 => "left_alt".into(),
        57 => "space".into(),
        97 => "right_ctrl".into(),
        100 => "right_alt".into(),
        103 => "up".into(),
        105 => "left".into(),
        106 => "right".into(),
        108 => "down".into(),
        125 => "left_meta".into(),
        126 => "right_meta".into(),
        2..=11 => ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"][(code - 2) as usize].into(),
        16..=25 => ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"][(code - 16) as usize].into(),
        30..=38 => ["a", "s", "d", "f", "g", "h", "j", "k", "l"][(code - 30) as usize].into(),
        44..=50 => ["z", "x", "c", "v", "b", "n", "m"][(code - 44) as usize].into(),
        59..=68 => format!("f{}", code - 58),
        87 => "f11".into(),
        88 => "f12".into(),
        _ => format!("code_{code}"),
    }
}

fn button_name(code: u16) -> String {
    match code {
        272 => "mouse.button.left".into(),
        273 => "mouse.button.right".into(),
        274 => "mouse.button.middle".into(),
        275 => "mouse.button.side".into(),
        276 => "mouse.button.extra".into(),
        304 => "gamepad.button.south".into(),
        305 => "gamepad.button.east".into(),
        307 => "gamepad.button.north".into(),
        308 => "gamepad.button.west".into(),
        310 => "gamepad.button.left_shoulder".into(),
        311 => "gamepad.button.right_shoulder".into(),
        314 => "gamepad.button.select".into(),
        315 => "gamepad.button.start".into(),
        316 => "gamepad.button.mode".into(),
        317 => "gamepad.button.left_stick".into(),
        318 => "gamepad.button.right_stick".into(),
        _ => format!("button.{code}"),
    }
}

fn control_name(class: &DeviceClass, event_type: u16, code: u16) -> String {
    match event_type {
        EV_KEY if matches!(class, DeviceClass::Keyboard) && code < 272 => {
            format!("keyboard.key.{}", key_name(code))
        }
        EV_KEY => button_name(code),
        EV_REL => match code {
            0 => "mouse.relative.x".into(),
            1 => "mouse.relative.y".into(),
            6 => "mouse.wheel.horizontal".into(),
            8 => "mouse.wheel.vertical".into(),
            _ => format!("relative.{code}"),
        },
        EV_ABS => match code {
            0 => "gamepad.stick.left.x".into(),
            1 => "gamepad.stick.left.y".into(),
            2 => "gamepad.trigger.left".into(),
            3 => "gamepad.stick.right.x".into(),
            4 => "gamepad.stick.right.y".into(),
            5 => "gamepad.trigger.right".into(),
            16 => "gamepad.dpad.x".into(),
            17 => "gamepad.dpad.y".into(),
            47 => "touch.slot".into(),
            53 => "touch.x".into(),
            54 => "touch.y".into(),
            57 => "touch.tracking_id".into(),
            _ => format!("axis.{code}"),
        },
        _ => format!("event.{event_type}.{code}"),
    }
}

fn kind(class: &DeviceClass, event_type: u16, code: u16) -> &'static str {
    match event_type {
        EV_KEY if matches!(class, DeviceClass::Keyboard) && code < 272 => "key",
        EV_KEY => "button",
        EV_REL => "relative",
        EV_ABS if code == 16 || code == 17 => "hat",
        EV_ABS if matches!(class, DeviceClass::Touchpad) => "touch",
        EV_ABS => "axis",
        _ => "raw",
    }
}

fn parse_bitmap(value: &str) -> Vec<u16> {
    let bits = usize::BITS as usize;
    let mut result = Vec::new();
    for (word_index, word) in value.split_whitespace().rev().enumerate() {
        if let Ok(parsed) = usize::from_str_radix(word, 16) {
            for bit in 0..bits {
                if parsed & (1usize << bit) != 0 {
                    if let Ok(code) = u16::try_from(word_index * bits + bit) {
                        result.push(code);
                    }
                }
            }
        }
    }
    result
}

fn bitmap_for(node: &str, name: &str) -> Vec<u16> {
    let Some(event) = Path::new(node).file_name() else {
        return Vec::new();
    };
    fs::read_to_string(
        Path::new("/sys/class/input")
            .join(event)
            .join("device/capabilities")
            .join(name),
    )
    .map(|value| parse_bitmap(&value))
    .unwrap_or_default()
}

fn eviocgabs(code: u16) -> libc::c_ulong {
    const IOC_READ: libc::c_ulong = 2;
    (IOC_READ << 30)
        | ((size_of::<InputAbsInfo>() as libc::c_ulong) << 16)
        | ((b'E' as libc::c_ulong) << 8)
        | (0x40 + code as libc::c_ulong)
}

fn axis_info(fd: RawFd, code: u16) -> Option<InputAbsInfo> {
    let mut info = InputAbsInfo::default();
    let result = unsafe { libc::ioctl(fd, eviocgabs(code), &mut info) };
    (result >= 0).then_some(info)
}

pub fn capabilities(device: &DeviceRecord) -> serde_json::Value {
    let mut controls = BTreeMap::<String, InputControl>::new();
    for node in event_nodes(device) {
        let file = File::open(&node).ok();
        for (event_type, capability) in [(EV_KEY, "key"), (EV_REL, "rel"), (EV_ABS, "abs")] {
            for code in bitmap_for(&node, capability) {
                let info = file
                    .as_ref()
                    .filter(|_| event_type == EV_ABS)
                    .and_then(|file| axis_info(file.as_raw_fd(), code));
                let control = control_name(&device.class, event_type, code);
                controls.entry(control.clone()).or_insert(InputControl {
                    control,
                    kind: kind(&device.class, event_type, code),
                    code,
                    minimum: info.as_ref().map(|item| item.minimum),
                    maximum: info.as_ref().map(|item| item.maximum),
                });
            }
        }
    }
    serde_json::json!({
        "device_id": device.id,
        "device_class": device.class,
        "controls": controls.into_values().collect::<Vec<_>>(),
        "nodes": event_nodes(device),
        "safety": "read-only",
    })
}

fn open_nodes(device: &DeviceRecord) -> io::Result<Vec<(String, File)>> {
    let mut files = Vec::new();
    let mut last_error = None;
    for node in event_nodes(device) {
        match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NONBLOCK)
            .open(&node)
        {
            Ok(file) => files.push((node, file)),
            Err(error) => last_error = Some(error),
        }
    }
    if files.is_empty() {
        return Err(last_error.unwrap_or_else(|| {
            io::Error::new(io::ErrorKind::NotFound, "no evdev node for this device")
        }));
    }
    Ok(files)
}

pub fn stream_events(
    device: &DeviceRecord,
    stream: &mut UnixStream,
    stop: &Arc<AtomicBool>,
) -> io::Result<()> {
    let files = open_nodes(device)?;
    let mut ranges = BTreeMap::new();
    for (index, (_node, file)) in files.iter().enumerate() {
        for code in bitmap_for(&files[index].0, "abs") {
            if let Some(info) = axis_info(file.as_raw_fd(), code) {
                ranges.insert((index, code), (info.minimum, info.maximum));
            }
        }
    }
    let mut poll_fds = files
        .iter()
        .map(|(_node, file)| libc::pollfd {
            fd: file.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        })
        .collect::<Vec<_>>();
    let mut buffer = [0u8; size_of::<RawInputEvent>() * 64];
    while !stop.load(Ordering::Relaxed) {
        let ready = unsafe { libc::poll(poll_fds.as_mut_ptr(), poll_fds.len() as _, 250) };
        if ready < 0 {
            return Err(io::Error::last_os_error());
        }
        for (index, descriptor) in poll_fds.iter_mut().enumerate() {
            if descriptor.revents & libc::POLLIN == 0 {
                continue;
            }
            let count =
                unsafe { libc::read(descriptor.fd, buffer.as_mut_ptr().cast(), buffer.len()) };
            if count <= 0 {
                continue;
            }
            for chunk in buffer[..count as usize].chunks_exact(size_of::<RawInputEvent>()) {
                let event =
                    unsafe { std::ptr::read_unaligned(chunk.as_ptr().cast::<RawInputEvent>()) };
                if !matches!(event.event_type, EV_KEY | EV_REL | EV_ABS) {
                    continue;
                }
                let range = ranges.get(&(index, event.code));
                let normalized = range.and_then(|(minimum, maximum)| {
                    (*maximum != *minimum).then(|| {
                        if event.code == 2 || event.code == 5 {
                            (event.value - minimum) as f64 / (maximum - minimum) as f64
                        } else {
                            ((event.value - minimum) as f64 / (maximum - minimum) as f64) * 2.0
                                - 1.0
                        }
                    })
                });
                let payload = serde_json::json!({
                    "event": "input",
                    "device_id": device.id,
                    "timestamp_us": event.time.tv_sec as i64 * 1_000_000 + event.time.tv_usec as i64,
                    "kind": kind(&device.class, event.event_type, event.code),
                    "control": control_name(&device.class, event.event_type, event.code),
                    "raw_value": event.value,
                    "normalized_value": normalized,
                    "node": files[index].0,
                });
                writeln!(stream, "{}", payload)?;
                stream.flush()?;
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_kernel_capability_bitmaps() {
        assert_eq!(parse_bitmap("0 3"), vec![0, 1]);
        assert_eq!(parse_bitmap("1 0"), vec![usize::BITS as u16]);
    }

    #[test]
    fn normalizes_standard_gamepad_names() {
        assert_eq!(
            control_name(&DeviceClass::Gamepad, EV_KEY, 304),
            "gamepad.button.south"
        );
        assert_eq!(
            control_name(&DeviceClass::Gamepad, EV_ABS, 3),
            "gamepad.stick.right.x"
        );
    }
}
