# Deblestia — Debian × Caelestia

[Français](README.md) · **English**

Deblestia provides a modular Debian and Hyprland desktop with Deblestia Bar,
Nova, Nova Lite, Nova Shell, MPVpaper Engine, PeriphX and MirrorBridge. Existing
component installers remain available.

## Screenshots

### Deblestia Bar

| Desktop and HUD | Application launcher |
| --- | --- |
| ![Deblestia Bar desktop](docs/images/deblestia-bar-desktop.png) | ![Deblestia Bar launcher](docs/images/deblestia-bar-launcher.png) |

### Deblestia Nova 2

| Multi-monitor bar | Session menu |
| --- | --- |
| ![Deblestia Nova 2 desktop](docs/images/deblestia-nova2-desktop.png) | ![Deblestia Nova 2 session menu](docs/images/deblestia-nova2-session.png) |

### Deblestia Nova Lite

| Dashboard | Control center |
| --- | --- |
| ![Deblestia Nova Lite dashboard](docs/images/deblestia-nova-lite-dashboard.png) | ![Deblestia Nova Lite control center](docs/images/deblestia-nova-lite-control-center.png) |

## Quick installation

Deblestia Setup scans the computer, recommends a performance profile and keeps
GNOME and the existing display manager installed. It shows the complete plan
before asking for confirmation.

```bash
git clone --depth 1 https://github.com/kebemouhamet08-gif/Debian-Hyprland-Custom.git
cd Debian-Hyprland-Custom
./install.sh --lang en
```

The system locale is detected automatically. You can force either supported
language with `--lang en`, `--lang fr`, or the `DEBLESTIA_LANG` environment
variable:

```bash
DEBLESTIA_LANG=en ./install.sh
./install.sh --lang en diagnostic
./install.sh --lang en --dry-run
```

## Installation modes

- `./install.sh --lang en automatic` scans the system and installs the suggested profile.
- `./install.sh --lang en manual` lets you choose individual components.
- `./install.sh --lang en diagnostic` only prints the hardware and compatibility report.
- `./install.sh --lang en --dry-run` prints the installation plan without changing the system.
- `./install.sh --lang en uninstall` restores files recorded by the unified installer.

## Individual components

The legacy entry points remain available:

```text
install-deblestia-bar.sh
install-deblestia-nova.sh
install-deblestia-nova-lite.sh
install-deblestia-shell.sh
install-deblestia-nova2.sh
install-deblestia-nova-shell.sh
install-custom-debian-v2.sh
install-mpvpaper-engine.sh
install-periphx.sh
install-mirrorbridge.sh
```

Run an installer with `check` before `install`, for example:

```bash
./install-mpvpaper-engine.sh check
./install-mpvpaper-engine.sh install
```

## Contributing

```bash
DEBLESTIA_LANG=en ./contribute.sh report
DEBLESTIA_LANG=en ./contribute.sh test
```

The hardware report is anonymized and displayed locally. Deblestia does not send
diagnostic data automatically.

## License

See [LICENSE.md](LICENSE.md).
