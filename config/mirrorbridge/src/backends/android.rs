use super::spawn_and_reap;
use anyhow::Result;
use std::process::Command;

pub fn launch_scrcpy(serial: &str) -> Result<()> {
    spawn_and_reap(
        Command::new("scrcpy")
            .arg("-s")
            .arg(serial)
            .arg("--window-title")
            .arg(format!("MirrorBridge — {serial}")),
        "scrcpy",
    )
}
