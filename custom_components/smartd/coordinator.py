"""Data update coordinator for S.M.A.R.T. Disk Monitor."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

import asyncssh

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_ID_PENDING_SECTORS,
    ATTR_ID_REALLOCATED_SECTORS,
    ATTR_ID_UNCORRECTABLE_ERRORS,
    AUTH_TYPE_KEY,
    CONF_AUTH_TYPE,
    CONF_DEVICES,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSH_KEY,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE_NVME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _parse_smart_data(raw_json: str, device: str) -> dict[str, Any]:
    """Parse smartctl JSON output into a structured dict."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise ValueError(f"Failed to parse smartctl JSON for {device}: {err}") from err

    result: dict[str, Any] = {
        "available": True,
        "device": device,
        "smart_passed": None,
        "temperature": None,
        "power_on_hours": None,
        "reallocated_sectors": None,
        "pending_sectors": None,
        "uncorrectable_errors": None,
        "model_name": data.get("model_name") or data.get("model_family"),
        "serial_number": data.get("serial_number"),
        "firmware_version": data.get("firmware_version"),
        "capacity_bytes": (data.get("user_capacity") or {}).get("bytes"),
        "device_type": (data.get("device") or {}).get("type"),
        "rotation_rate": data.get("rotation_rate"),
    }

    # Overall SMART health status
    smart_status = data.get("smart_status") or {}
    result["smart_passed"] = smart_status.get("passed")

    # Temperature
    temperature = data.get("temperature") or {}
    result["temperature"] = temperature.get("current")

    # Power-on time
    power_on_time = data.get("power_on_time") or {}
    result["power_on_hours"] = power_on_time.get("hours")

    device_type = result["device_type"] or ""

    if device_type == DEVICE_TYPE_NVME:
        # NVMe drives expose health info in a dedicated log
        nvme_log = data.get("nvme_smart_health_information_log") or {}
        result["uncorrectable_errors"] = nvme_log.get("media_errors")
        # NVMe does not have reallocated/pending sectors in the traditional sense
    else:
        # ATA/SATA drives — parse attribute table
        ata_attrs = data.get("ata_smart_attributes") or {}
        attr_table = ata_attrs.get("table") or []
        for attr in attr_table:
            attr_id = attr.get("id")
            raw = (attr.get("raw") or {}).get("value")
            if attr_id == ATTR_ID_REALLOCATED_SECTORS:
                result["reallocated_sectors"] = raw
            elif attr_id == ATTR_ID_PENDING_SECTORS:
                result["pending_sectors"] = raw
            elif attr_id == ATTR_ID_UNCORRECTABLE_ERRORS:
                result["uncorrectable_errors"] = raw

    return result


class SmartdCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches SMART data from remote hosts via SSH."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.config_entry = config_entry

        data = config_entry.data
        self._host: str = data[CONF_HOST]
        self._port: int = data[CONF_PORT]
        self._username: str = data[CONF_USERNAME]
        self._auth_type: str = data[CONF_AUTH_TYPE]
        self._password: str | None = data.get(CONF_PASSWORD)
        self._ssh_key_pem: str | None = data.get(CONF_SSH_KEY)
        self._devices: list[str] = data[CONF_DEVICES]

    def _build_connect_kwargs(self) -> dict[str, Any]:
        """Build keyword arguments for asyncssh.connect."""
        kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "username": self._username,
            "known_hosts": None,
        }
        if self._auth_type == AUTH_TYPE_KEY and self._ssh_key_pem:
            kwargs["client_keys"] = [asyncssh.import_private_key(self._ssh_key_pem)]
            kwargs["password"] = None
        else:
            kwargs["password"] = self._password

        return kwargs

    async def _run_command(
        self,
        conn: asyncssh.SSHClientConnection,
        command: str,
    ) -> asyncssh.SSHCompletedProcess:
        """Run a command and return the completed process (never raises on non-zero)."""
        return await conn.run(command, check=False)

    async def _fetch_device_data(
        self,
        conn: asyncssh.SSHClientConnection,
        device: str,
    ) -> dict[str, Any]:
        """Fetch and parse SMART data for a single device."""
        command = f"smartctl -a {device} --json"
        proc = await self._run_command(conn, command)

        # smartctl uses a bitmask exit code:
        #   bit 0 (1)  : command line parsing error
        #   bit 1 (2)  : device could not be opened
        #   bit 2 (4)  : a checksum error was found
        #   bit 3 (8)  : SMART or ATA SMART status FAILED
        #   bits 4-7   : other info (self-test failures, errors logged, etc.)
        # Bits 0 and 1 indicate we cannot trust the output at all.
        returncode = (
            getattr(proc, "exit_status", None)
            or getattr(proc, "returncode", None)
            or 0
        )
        fatal_bits = returncode & 0b00000011  # bits 0 and 1
        if fatal_bits:
            _LOGGER.warning(
                "smartctl returned fatal exit code %d for %s on %s",
                returncode,
                device,
                self._host,
            )
            return {"available": False, "device": device}

        stdout = proc.stdout or ""
        if not stdout.strip():
            _LOGGER.warning("Empty output from smartctl for %s on %s", device, self._host)
            return {"available": False, "device": device}

        try:
            return _parse_smart_data(stdout, device)
        except ValueError as err:
            _LOGGER.error("Parse error for %s on %s: %s", device, self._host, err)
            return {"available": False, "device": device}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch SMART data for all configured devices."""
        connect_kwargs = self._build_connect_kwargs()

        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                results: dict[str, dict[str, Any]] = {}
                for device in self._devices:
                    results[device] = await self._fetch_device_data(conn, device)
                return results

        except asyncssh.PermissionDenied as err:
            # Auth failure is a config problem, not a transient one
            raise ConfigEntryAuthFailed(
                f"SSH authentication failed for {self._username}@{self._host}: {err}"
            ) from err
        except asyncssh.Error as err:
            raise UpdateFailed(
                f"SSH connection to {self._host}:{self._port} failed: {err}"
            ) from err
        except OSError as err:
            raise UpdateFailed(
                f"Network error connecting to {self._host}:{self._port}: {err}"
            ) from err


async def async_discover_devices(
    host: str,
    port: int,
    username: str,
    auth_type: str,
    password: str | None = None,
    ssh_key_pem: str | None = None,
) -> list[str]:
    """Discover SMART-capable block devices on the remote host.

    Returns a list of device paths (e.g. ['/dev/sda', '/dev/nvme0']).
    Falls back to empty list if smartctl --scan is unavailable.
    """
    connect_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": username,
        "known_hosts": None,
    }
    if auth_type == AUTH_TYPE_KEY and ssh_key_pem:
        connect_kwargs["client_keys"] = [asyncssh.import_private_key(ssh_key_pem)]
        connect_kwargs["password"] = None
    else:
        connect_kwargs["password"] = password

    async with asyncssh.connect(**connect_kwargs) as conn:
        proc = await conn.run("smartctl --scan --json", check=False)
        if not proc.stdout:
            return []
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return []

        devices = []
        for entry in data.get("devices") or []:
            name = entry.get("name")
            if name:
                devices.append(name)
        return devices
