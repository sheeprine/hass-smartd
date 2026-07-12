"""Sensor platform for S.M.A.R.T. Disk Monitor."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, CONF_PORT, DATA_COORDINATOR, DOMAIN
from .coordinator import SmartdCoordinator


@dataclass(frozen=True, kw_only=True)
class SmartdSensorEntityDescription(SensorEntityDescription):
    """Describes a S.M.A.R.T. sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    # Whether the sensor should be hidden when the value is None (no data)
    hide_when_none: bool = True


SENSOR_DESCRIPTIONS: tuple[SmartdSensorEntityDescription, ...] = (
    SmartdSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("temperature"),
    ),
    SmartdSensorEntityDescription(
        key="power_on_hours",
        translation_key="power_on_hours",
        native_unit_of_measurement="h",
        icon="mdi:clock-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.get("power_on_hours"),
    ),
    SmartdSensorEntityDescription(
        key="reallocated_sectors",
        translation_key="reallocated_sectors",
        native_unit_of_measurement="sectors",
        icon="mdi:harddisk-plus",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("reallocated_sectors"),
    ),
    SmartdSensorEntityDescription(
        key="pending_sectors",
        translation_key="pending_sectors",
        native_unit_of_measurement="sectors",
        icon="mdi:harddisk-remove",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("pending_sectors"),
    ),
    SmartdSensorEntityDescription(
        key="uncorrectable_errors",
        translation_key="uncorrectable_errors",
        native_unit_of_measurement="errors",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.get("uncorrectable_errors"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up S.M.A.R.T. sensor entities."""
    coordinator: SmartdCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        DATA_COORDINATOR
    ]
    host = config_entry.data[CONF_HOST]
    port = config_entry.data[CONF_PORT]

    entities: list[SmartdSensor] = []
    for device_path in coordinator.data or {}:
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                SmartdSensor(
                    coordinator=coordinator,
                    description=description,
                    device_path=device_path,
                    host=host,
                    port=port,
                )
            )

    async_add_entities(entities)


def _build_device_info(
    host: str,
    port: int,
    device_path: str,
    device_data: dict[str, Any],
) -> DeviceInfo:
    """Build a DeviceInfo object for the given disk."""
    model = device_data.get("model_name")
    serial = device_data.get("serial_number")
    firmware = device_data.get("firmware_version")

    if model and serial:
        device_name = f"{model} ({serial})"
    else:
        device_name = f"{host}:{device_path}"

    safe_path = device_path.replace("/", "_")
    device_unique_id = f"{host}_{port}{safe_path}"

    info = DeviceInfo(
        identifiers={(DOMAIN, device_unique_id)},
        name=device_name,
        manufacturer=None,
        model=model,
        sw_version=firmware,
        serial_number=serial,
        configuration_url=None,
    )
    return info


class SmartdSensor(CoordinatorEntity[SmartdCoordinator], SensorEntity):
    """A sensor that reports a single SMART attribute for one disk."""

    entity_description: SmartdSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartdCoordinator,
        description: SmartdSensorEntityDescription,
        device_path: str,
        host: str,
        port: int,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_path = device_path
        self._host = host
        self._port = port

        safe_path = device_path.replace("/", "_")
        self._attr_unique_id = f"{host}_{port}{safe_path}_{description.key}"

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return the coordinator data for this device."""
        return (self.coordinator.data or {}).get(self._device_path) or {}

    @property
    def available(self) -> bool:
        """Return False if the device data is unavailable."""
        return bool(self._device_data.get("available", False))

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self._device_data)

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
        capacity = d.get("capacity_bytes")
        attrs: dict[str, Any] = {
            "device_path": self._device_path,
            "device_type": d.get("device_type"),
        }
        if capacity is not None:
            attrs["capacity_gb"] = round(capacity / 1_000_000_000, 2)
        rotation_rate = d.get("rotation_rate")
        if rotation_rate is not None:
            attrs["rotation_rate_rpm"] = rotation_rate
        return attrs
