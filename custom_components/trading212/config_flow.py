"""Config flow for Trading212 integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from pytrading212api.api import Trading212API
from pytrading212api.exceptions import (
    Trading212BadApiKey,
    Trading212Limited,
    Trading212TimeOut,
)
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_SECRET, CONF_ACCOUNT_NAME, DOMAIN, POLLING_INTERVAL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT_NAME): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_API_SECRET): str,
    }
)


class Trading212ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Trading212."""

    VERSION = 1
    reauth_entry: ConfigEntry | None = None

    def __init__(self) -> None:
        """Initialise config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            trading212_api = Trading212API(
                api_key=user_input[CONF_API_KEY],
                api_secret=user_input[CONF_API_SECRET],
                session=async_get_clientsession(self.hass),
            )
            try:
                metadata = await trading212_api.get_account_metadata()

            except Trading212BadApiKey:
                errors["base"] = "bad_api_key"
            except Trading212TimeOut:
                errors["base"] = "timeout"
            except Trading212Limited:
                errors["base"] = "limited"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(metadata["id"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{user_input[CONF_ACCOUNT_NAME]} - ID:{metadata['id']}",
                    data={
                        CONF_ACCOUNT_NAME: user_input[CONF_ACCOUNT_NAME],
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_API_SECRET: user_input[CONF_API_SECRET],
                    },
                    options={CONF_SCAN_INTERVAL: POLLING_INTERVAL},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def async_step_reauth(
        self, user_input: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth."""
        self.reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        assert self.reauth_entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            entry_data = self.reauth_entry.data
            trading212_api = Trading212API(
                api_key=entry_data[CONF_API_KEY],
                api_secret=entry_data[CONF_API_SECRET],
                session=async_get_clientsession(self.hass),
            )
            try:
                await trading212_api.get_account_metadata()

                await self.hass.config_entries.async_reload(self.reauth_entry.entry_id)

                return self.async_abort(reason="reauth_successful")

            except Trading212BadApiKey:
                errors["base"] = "bad_api_key"
            except Trading212TimeOut:
                errors["base"] = "timeout"
            except Trading212Limited:
                errors["base"] = "limited"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error reauthenticating")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): str, vol.Required(CONF_API_SECRET): str}
            ),
            errors=errors,
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a options flow for Trading212."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=10)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
