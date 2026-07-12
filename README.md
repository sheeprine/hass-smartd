# S.M.A.R.T. Disk Monitor

[![HACS validation](https://github.com/sheeprine/hass-smartd/actions/workflows/hacs.yml/badge.svg)](https://github.com/sheeprine/hass-smartd/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/sheeprine/hass-smartd/actions/workflows/hassfest.yml/badge.svg)](https://github.com/sheeprine/hass-smartd/actions/workflows/hassfest.yml)

A Home Assistant custom integration that monitors remote disk health using [smartmontools](https://www.smartmontools.org/) (`smartctl`) over SSH.

## Features

- Connects to remote Linux hosts via SSH (password or private key)
- Auto-discovers SMART-capable block devices
- Supports both SATA/ATA and NVMe drives
- Exposes per-disk entities in Home Assistant:
  - **SMART health** — binary sensor (problem / passed)
  - **Temperature** — in °C
  - **Power-on hours**
  - **Reallocated sectors** (ATA only)
  - **Pending sectors** (ATA only)
  - **Uncorrectable errors**

## Requirements

- `smartmontools` installed on the remote host
- SSH user with permission to run `smartctl` (via sudo or capabilities)

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **Custom repositories**
3. Add `https://github.com/sheeprine/hass-smartd` with category **Integration**
4. Install **S.M.A.R.T. Disk Monitor**
5. Restart Home Assistant

### Manual

Copy `custom_components/smartd/` into your HA `config/custom_components/` directory and restart.

## Configuration

Go to **Settings → Devices & Services → Add Integration → S.M.A.R.T. Disk Monitor** and follow the setup flow:

1. Enter the hostname, SSH port, and username
2. Choose authentication method (password or SSH private key)
3. Select which block devices to monitor (auto-discovered via `smartctl --scan`)

## Remote host setup

The SSH user must be able to run `smartctl` without a TTY. The simplest approach is a sudoers entry:

```
your_user ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
```

Or grant the capability directly to the binary:

```bash
sudo setcap cap_sys_rawio+ep /usr/sbin/smartctl
```
