# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development setup

No build step — this is a Home Assistant custom component. To develop against real HA:

```bash
# Install HA and asyncssh in a virtual environment
pip install homeassistant asyncssh==2.18.0

# For type checking
pip install pyright

# Run pyright (from repo root)
pyright custom_components/smartd
```

To test the integration manually, copy `custom_components/smartd/` into your HA `config/custom_components/` directory and restart HA. Add via **Settings → Devices & Services → Add Integration → S.M.A.R.T. Disk Monitor**.

The remote host must have `smartmontools` installed and the SSH user must be able to run `smartctl` (typically via sudo or setuid/capabilities on the binary).

## Architecture

All logic lives in `custom_components/smartd/`. The integration follows standard HA patterns:

**Data flow:** `ConfigFlow` → creates a `ConfigEntry` → `SmartdCoordinator` (one per entry) fetches all device data over a single SSH connection every 5 minutes → sensor/binary_sensor entities read from coordinator data.

**`coordinator.py`** is the core. `SmartdCoordinator._async_update_data()` opens one SSH connection per poll cycle, runs `smartctl -a <device> --json` for each configured device, and returns `dict[device_path, parsed_data]`. Key parsing detail: smartctl exit codes are a **bitmask** — only bits 0 and 1 (command/open failure) indicate invalid output; bit 3 (SMART FAILED) still produces valid JSON and must not be treated as an error. NVMe vs ATA is branched on `device.type == "nvme"` in the JSON output.

**`config_flow.py`** runs a 4-step UI flow: host details → credentials (password or PEM key) → SSH connection test + `smartctl --scan --json` discovery → device multi-select. Discovery is best-effort; the flow continues with free-text entry if it fails.

**`sensor.py`** uses a `SmartdSensorEntityDescription` dataclass (extends `SensorEntityDescription`) with a `value_fn` lambda, so all 5 sensor types are driven from a single `SENSOR_DESCRIPTIONS` tuple. The `_build_device_info()` helper is shared with `binary_sensor.py` to ensure both platforms register entities under the same HA Device.

**`binary_sensor.py`** exposes a single `PROBLEM`-class binary sensor per disk. `is_on = not smart_passed` (True = problem).

## HA-specific conventions

- `CONF_*` constants that overlap with `homeassistant.const` (HOST, PORT, USERNAME, PASSWORD) are re-declared in `const.py` for import consistency across the package.
- Entities use `_attr_has_entity_name = True` with `translation_key`; all display names live in `strings.json` / `translations/en.json`.
- Auth failures raise `ConfigEntryAuthFailed` (triggers HA re-auth UI); transient SSH errors raise `UpdateFailed` (triggers coordinator retry).
- Minimum HA version: **2024.1.0** (required by HACS).
