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

### Public key authentication

Using a dedicated SSH key pair is recommended over password auth.

**1. Generate a key pair** (on your Home Assistant host or any machine you control):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/smartd_id -C "hass-smartd" -N ""
```

This creates `smartd_id` (private key) and `smartd_id.pub` (public key).

**2. Authorize the public key on the remote host with command restriction:**

Create a wrapper script that only allows `smartctl` invocations:

```bash
sudo tee /usr/local/bin/smartctl-wrapper > /dev/null << 'EOF'
#!/bin/bash
if [[ "$SSH_ORIGINAL_COMMAND" =~ ^smartctl[[:space:]] ]]; then
    exec $SSH_ORIGINAL_COMMAND
fi
echo "Denied: $SSH_ORIGINAL_COMMAND" >&2
exit 1
EOF
sudo chmod 755 /usr/local/bin/smartctl-wrapper
```

Then add the public key to `~/.ssh/authorized_keys` with a forced command and all other SSH features disabled:

```bash
mkdir -p ~/.ssh
echo "restrict,command=\"/usr/local/bin/smartctl-wrapper\" $(cat ~/.ssh/smartd_id.pub)" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

With this setup, the key can only be used to run `smartctl` commands — interactive shells, port forwarding, and X11 forwarding are all blocked.

**3. Paste the private key into the integration setup.** During the configuration flow, choose **SSH private key** as the authentication method and paste the contents of `~/.ssh/smartd_id` (the private key, not the `.pub` file). The integration expects PEM format; keys generated with `ssh-keygen` default to this format.
