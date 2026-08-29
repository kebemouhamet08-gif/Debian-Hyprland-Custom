use anyhow::{anyhow, Context, Result};
use std::process::Command;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AndroidDevice {
    pub serial: String,
    pub model: String,
    pub state: String,
}

impl AndroidDevice {
    pub fn is_ready(&self) -> bool {
        self.state == "device"
    }
}

pub fn adb_available() -> bool {
    Command::new("adb")
        .arg("version")
        .output()
        .is_ok_and(|output| output.status.success())
}

pub fn list_android_devices() -> Result<Vec<AndroidDevice>> {
    let output = Command::new("adb")
        .args(["devices", "-l"])
        .output()
        .context("impossible de lancer ADB")?;

    if !output.status.success() {
        return Err(anyhow!(
            "ADB a retourné une erreur : {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }

    Ok(parse_adb_devices(&String::from_utf8_lossy(&output.stdout)))
}

pub fn parse_adb_devices(output: &str) -> Vec<AndroidDevice> {
    output
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty()
                || line.starts_with("List of devices attached")
                || line.starts_with('*')
            {
                return None;
            }

            let mut fields = line.split_whitespace();
            let serial = fields.next()?;
            let state = fields.next().unwrap_or("unknown");
            let mut model = String::from("Android");

            for field in fields {
                if let Some(value) = field.strip_prefix("model:") {
                    model = value.replace('_', " ");
                }
            }

            Some(AndroidDevice {
                serial: serial.to_owned(),
                model,
                state: state.to_owned(),
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_one_android_device() {
        let input = "List of devices attached\nABC123\tdevice product:husky model:Pixel_8_Pro device:husky transport_id:1\n";
        let devices = parse_adb_devices(input);

        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].serial, "ABC123");
        assert_eq!(devices[0].model, "Pixel 8 Pro");
        assert_eq!(devices[0].state, "device");
        assert!(devices[0].is_ready());
    }

    #[test]
    fn parses_unauthorized_device() {
        let input = "List of devices attached\nABC123\tunauthorized\n";
        let devices = parse_adb_devices(input);

        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].state, "unauthorized");
        assert!(!devices[0].is_ready());
    }

    #[test]
    fn ignores_adb_daemon_messages() {
        let input = "* daemon not running; starting now at tcp:5037\n* daemon started successfully\nList of devices attached\n\n";
        assert!(parse_adb_devices(input).is_empty());
    }
}
