"""Binary sensor platform for S.M.A.R.T. Disk Monitor."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, CONF_PORT, DATA_COORDINATOR, DOMAIN
from .coordinator import SmartdCoordinator
from .sensor import _build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up S.M.A.R.T. binary sensor entities."""
    coordinator: SmartdCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        DATA_COORDINATOR
    ]
    host = config_entry.data[CONF_HOST]
    port = config_entry.data[CONF_PORT]

    entities = [
        SmartdHealthBinarySensor(
            coordinator=coordinator,
            device_path=device_path,
            host=host,
            port=port,
        )
        for device_path in coordinator.data or {}
    ]
    async_add_entities(entities)


class SmartdHealthBinarySensor(CoordinatorEntity[SmartdCoordinator], BinarySensorEntity):
    """Binary sensor representing the overall SMART health of a disk.

    Device class PROBLEM:
      is_on = True  → there IS a problem (SMART status FAILED)
      is_on = False → the disk is healthy (SMART status PASSED)
    """

    _attr_has_entity_name = True
    _attr_translation_key = "health"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: SmartdCoordinator,
        device_path: str,
        host: str,
        port: int,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        self._device_path = device_path
        self._host = host
        self._port = port

        safe_path = device_path.replace("/", "_")
        self._attr_unique_id = f"{host}_{port}{safe_path}_health"

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return the coordinator data for this device."""
        return (self.coordinator.data or {}).get(self._device_path) or {}

    @property
    def available(self) -> bool:
        """Return False if the device data is unavailable."""
        return bool(self._device_data.get("available", False))

    @property
    def is_on(self) -> bool | None:
        """Return True when SMART status FAILED (i.e. there is a problem).

        Returns None when the health status is unknown.
        """
        passed = self._device_data.get("smart_passed")
        if passed is None:
            return None
        # PROBLEM device class: True = problem detected
        return not passed

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _build_device_info(
            self._host, self._port, self._device_path, self._device_data
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        d = self._device_data
        attrs: dict[str, Any] = {
            "device_path": self._device_path,
            "serial_number": d.get("serial_number"),
            "firmware_version": d.get("firmware_version"),
            "device_type": d.get("device_type"),
        }
        capacity = d.get("capacity_bytes")
        if capacity is not None:
            attrs["capacity_gb"] = round(capacity / 1_000_000_000, 2)
        return attrs
