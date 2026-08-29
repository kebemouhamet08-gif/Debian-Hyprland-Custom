use super::spawn_and_reap;
use anyhow::Result;
use std::process::Command;

pub fn launch_uxplay() -> Result<()> {
    spawn_and_reap(
        Command::new("uxplay").args(["-n", "MirrorBridge"]),
        "UxPlay",
    )
}
