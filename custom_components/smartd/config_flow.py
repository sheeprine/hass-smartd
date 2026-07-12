"""Config flow for S.M.A.R.T. Disk Monitor."""
from __future__ import annotations

import logging
from typing import Any

import asyncssh
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AUTH_TYPE_KEY,
    AUTH_TYPE_PASSWORD,
    CONF_AUTH_TYPE,
    CONF_DEVICES,
    CONF_SSH_KEY,
    DEFAULT_PORT,
    DOMAIN,
)
from .coordinator import async_discover_devices, async_test_connection

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_AUTH_TYPE, default=AUTH_TYPE_PASSWORD): vol.In(
            [AUTH_TYPE_PASSWORD, AUTH_TYPE_KEY]
        ),
    }
)


class SmartdConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for S.M.A.R.T. Disk Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._username: str = ""
        self._auth_type: str = AUTH_TYPE_PASSWORD
        self._password: str | None = None
        self._ssh_key_pem: str | None = None
        self._discovered_devices: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: host + auth type selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input[CONF_PORT]
            self._username = user_input[CONF_USERNAME]
            self._auth_type = user_input[CONF_AUTH_TYPE]

            # Prevent duplicate entries for the same host+port
            await self.async_set_unique_id(f"{self._host}_{self._port}")
            self._abort_if_unique_id_configured()

            if self._auth_type == AUTH_TYPE_KEY:
                return await self.async_step_key()
            return await self.async_step_password()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Required(CONF_USERNAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        CONF_AUTH_TYPE, default=AUTH_TYPE_PASSWORD
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=AUTH_TYPE_PASSWORD,
                                    label="Password",
                                ),
                                SelectOptionDict(
                                    value=AUTH_TYPE_KEY,
                                    label="SSH Private Key",
                                ),
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle password authentication step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._password = user_input[CONF_PASSWORD]
            errors = await self._async_test_and_discover()
            if not errors:
                return await self.async_step_devices()

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"host": self._host, "username": self._username},
        )

    async def async_step_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle SSH private key authentication step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._ssh_key_pem = user_input[CONF_SSH_KEY]
            errors = await self._async_test_and_discover()
            if not errors:
                return await self.async_step_devices()

        return self.async_show_form(
            step_id="key",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SSH_KEY): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT,
                            multiline=True,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"host": self._host, "username": self._username},
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_DEVICES) or []
            if not selected:
                errors[CONF_DEVICES] = "no_devices_selected"
            else:
                return self._async_create_entry(selected)

        # Build options for the multi-select
        device_options = [
            SelectOptionDict(value=dev, label=dev)
            for dev in self._discovered_devices
        ]

        schema: vol.Schema
        if device_options:
            schema = vol.Schema(
                {
                    vol.Required(CONF_DEVICES): SelectSelector(
                        SelectSelectorConfig(
                            options=device_options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                            custom_value=True,
                        )
                    ),
                }
            )
        else:
            # No devices discovered — allow free-text entry
            schema = vol.Schema(
                {
                    vol.Required(CONF_DEVICES): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            )

        return self.async_show_form(
            step_id="devices",
            data_schema=schema,
            errors=errors,
            description_placeholders={"host": self._host},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _async_test_and_discover(self) -> dict[str, str]:
        """Test the SSH connection and attempt device discovery.

        Returns a dict of errors (empty means success).
        """
        try:
            await async_test_connection(
                host=self._host,
                port=self._port,
                username=self._username,
                auth_type=self._auth_type,
                password=self._password,
                ssh_key_pem=self._ssh_key_pem,
            )
        except asyncssh.PermissionDenied:
            return {"base": "invalid_auth"}
        except asyncssh.Error:
            return {"base": "cannot_connect"}
        except OSError:
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during SSH connection test")
            return {"base": "unknown"}

        # Best-effort device discovery — don't fail the flow if unavailable
        try:
            self._discovered_devices = await async_discover_devices(
                host=self._host,
                port=self._port,
                username=self._username,
                auth_type=self._auth_type,
                password=self._password,
                ssh_key_pem=self._ssh_key_pem,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Device discovery failed for %s; user will enter devices manually",
                self._host,
            )
            self._discovered_devices = []

        return {}

    def _async_create_entry(self, devices: list[str]) -> ConfigFlowResult:
        """Create the config entry."""
        data: dict[str, Any] = {
            CONF_HOST: self._host,
            CONF_PORT: self._port,
            CONF_USERNAME: self._username,
            CONF_AUTH_TYPE: self._auth_type,
            CONF_DEVICES: devices,
        }
        if self._auth_type == AUTH_TYPE_PASSWORD:
            data[CONF_PASSWORD] = self._password
        else:
            data[CONF_SSH_KEY] = self._ssh_key_pem

        return self.async_create_entry(
            title=f"{self._username}@{self._host}:{self._port}",
            data=data,
        )
