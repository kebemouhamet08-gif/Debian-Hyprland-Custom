pub mod android;
pub mod ios;

use anyhow::{Context, Result};
use std::process::{Command, Stdio};

pub fn command_available(command: &str) -> bool {
    Command::new(command)
        .arg("--help")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok()
}

pub(crate) fn spawn_and_reap(command: &mut Command, description: &str) -> Result<()> {
    let mut child = command
        .stdin(Stdio::null())
        .spawn()
        .with_context(|| format!("impossible de lancer {description}"))?;

    std::thread::spawn(move || {
        let _ = child.wait();
    });

    Ok(())
}
