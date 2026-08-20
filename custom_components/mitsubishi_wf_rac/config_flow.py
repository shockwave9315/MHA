"""Config flow WF-RAC"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any
from uuid import uuid4

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries, exceptions
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import (
    CONF_BASE,
    CONF_DEVICE_ID,
    CONF_FORCE_UPDATE,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_AIRCO_ID,
    CONF_AVAILABILITY_RETRY_LIMIT,
    CONF_FIRMWARE_UPDATE_CHECK,
    CONF_OPERATOR_ID,
    CONF_INDOOR_OFFSET,
    CONF_OUTDOOR_OFFSET,
    CONF_TARGET_OFFSET,
    CONF_TARGET_OFFSET_COOL,
    CONF_TARGET_OFFSET_HEAT,
    DOMAIN,
)
from .wfrac.device import AVAILABILITY_FAILURE_LIMIT_MIN
from .wfrac.repository import AirconApiError, Repository

_LOGGER = logging.getLogger(__name__)


class WfRacConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 5
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL
    _discovery_info: dict[str, Any] = {}
    DOMAIN = DOMAIN

    def is_matching(self, other_flow: "WfRacConfigFlow") -> bool:
        """Return True if two flows are attempting to configure the same device."""
        if self.unique_id and other_flow.unique_id:
            return self.unique_id == other_flow.unique_id
        return False

    def _find_entry_matching(
        self, key: str, matches: Callable[[Any], bool]
    ) -> config_entries.ConfigEntry | None:
        """Returns the first entry where matches(entry.data[key]) returns True"""
        for entry in self._async_current_entries():
            if key in entry.data and matches(entry.data[key]):
                return entry
        return None

    def _find_entry_matching_option(
        self, key: str, matches: Callable[[Any], bool]
    ) -> config_entries.ConfigEntry | None:
        """Returns the first entry where matches(entry.options[key]) returns True"""
        for entry in self._async_current_entries():
            if key in entry.options and matches(entry.options[key]):
                return entry
        return None

    async def _async_register_airco(
            self,
            hass: HomeAssistant,
            data: dict[str, Any],
            exclude_entry_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate the user input allows us to connect, and register with the airco device"""
        if len(data[CONF_HOST]) < 3:
            raise InvalidHost
        if len(data[CONF_NAME]) < 3:
            raise InvalidName
        if not data.get(CONF_FORCE_UPDATE):
            existing_entry = self._find_entry_matching_option(
                CONF_HOST, lambda h: h == data[CONF_HOST]
            )
            if existing_entry and existing_entry.entry_id != exclude_entry_id:
                raise HostAlreadyConfigured(error_name=existing_entry.data[CONF_NAME])

        repository = Repository(
            hass,
            data[CONF_HOST],
            data[CONF_PORT],
            data[CONF_OPERATOR_ID],
            data[CONF_DEVICE_ID],
        )
        try:
            airco_id = await repository.get_airco_id()
        except (AirconApiError, KeyError, TypeError) as query_failed:
            raise CannotConnect(reason=str(query_failed)) from query_failed

        data[CONF_AIRCO_ID] = airco_id
        if not airco_id:
            raise CannotConnect(reason="unknown reason")

        _LOGGER.info(
            "Trying to register OperatorId[%s] on Airco[%s]",
            data[CONF_OPERATOR_ID],
            data[CONF_AIRCO_ID],
        )
        result = await repository.update_account_info(airco_id, hass.config.time_zone)
        if not result:
            raise CannotConnect
        if int(result["result"]) == 2:
            raise TooManyDevicesRegistered
        return data

    async def _async_fetch_operator_id(self) -> str:
        """Fetch UUID operator id if exists otherwise create it"""
        entry = self._find_entry_matching(CONF_OPERATOR_ID, bool)
        if entry:
            return str(entry.data[CONF_OPERATOR_ID])
        return f"hassio-{str(uuid4())[7:]}"

    async def _async_fetch_device_id(self) -> str:
        """Fetch unique device id if exists otherwise create it"""
        entry = self._find_entry_matching(CONF_DEVICE_ID, bool)
        if entry:
            return str(entry.data[CONF_DEVICE_ID])
        return f"homeassistant-device-{uuid4().hex[21:]}"

    async def _async_create_common(
            self,
            step_id: str,
            data_schema: vol.Schema,
            user_input: dict[str, Any] | None = None,
            description_placeholders: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Create a new entry"""
        errors: dict[str, str] = {}
        description_placeholders = description_placeholders or {}
        if user_input:
            description_placeholders["error_name"] = ""
            try:
                user_input[CONF_OPERATOR_ID] = await self._async_fetch_operator_id()
                user_input[CONF_DEVICE_ID] = await self._async_fetch_device_id()
                info = await self._async_register_airco(self.hass, user_input)
                data_input = user_input.copy()
                options_input = {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_AVAILABILITY_RETRY_LIMIT: AVAILABILITY_FAILURE_LIMIT_MIN,
                    CONF_FIRMWARE_UPDATE_CHECK: False,
                }
                data_input.pop(CONF_HOST)
                return self.async_create_entry(
                    title=info[CONF_NAME], data=data_input, options=options_input,
                )
            except KnownError as error:
                _LOGGER.error("create failed")
                errors, placeholders = error.get_errors_and_placeholders(data_schema.schema)
                errors.update(errors)
                for key, value in placeholders.items():
                    description_placeholders[key] = str(value) if isinstance(value, dict) else value
            except Exception:  # pylint: disable=broad-except
                _LOGGER.error("Unexpected exception", exc_info=True)
                errors[CONF_BASE] = "unexpected_error"
        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    def _field(
        user_input: dict[str, Any] | None,
        name: str,
        which: Callable[..., Any],
        default: Any = None,
    ) -> Any:
        """Helper for creating schema fields"""
        value = user_input.get(name, default) if user_input else default
        description = {"suggested_value": value} if value is not None else None
        return which(name, description=description)

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding device discovered by zeroconf."""
        description_placeholders = {
            "id": self._discovery_info[CONF_NAME],
            "host": self._discovery_info[CONF_HOST],
            "port": self._discovery_info[CONF_PORT],
        }
        if user_input:
            user_input[CONF_HOST] = self._discovery_info[CONF_HOST]
            user_input.setdefault(CONF_PORT, self._discovery_info[CONF_PORT])

        field = partial(self._field, user_input)
        data_schema = vol.Schema(
            {
                field(CONF_NAME, vol.Required, f"Airco {self._discovery_info[CONF_NAME]}"): str,
                field(CONF_PORT, vol.Optional, self._discovery_info[CONF_PORT]): cv.port,
            }
        )
        return await self._async_create_common(
            step_id="discovery_confirm",
            data_schema=data_schema,
            user_input=user_input,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return WfRacOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding device manually."""
        field = partial(self._field, user_input)
        data_schema = vol.Schema(
            {
                field(CONF_NAME, vol.Required, "Airco unknown"): cv.string,
                field(CONF_HOST, vol.Required): cv.string,
                field(CONF_PORT, vol.Optional, 51443): cv.port,
                field(CONF_FORCE_UPDATE, vol.Optional, False): cv.boolean,
            }
        )
        return await self._async_create_common(
            step_id="user", data_schema=data_schema, user_input=user_input
        )

    async def async_step_reconfigure(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle changing an existing entry's connection details (host/port/name)."""
        reconfigure_entry = self._get_reconfigure_entry()
        current = {
            CONF_NAME: reconfigure_entry.data[CONF_NAME],
            CONF_HOST: reconfigure_entry.options[CONF_HOST],
            CONF_PORT: reconfigure_entry.data[CONF_PORT],
        }
        field = partial(self._field, user_input or current)
        data_schema = vol.Schema(
            {
                field(CONF_NAME, vol.Required): cv.string,
                field(CONF_HOST, vol.Required): cv.string,
                field(CONF_PORT, vol.Optional, 51443): cv.port,
            }
        )
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input:
            try:
                data = dict(user_input)
                data[CONF_OPERATOR_ID] = reconfigure_entry.data[CONF_OPERATOR_ID]
                data[CONF_DEVICE_ID] = reconfigure_entry.data[CONF_DEVICE_ID]
                info = await self._async_register_airco(
                    self.hass, data, exclude_entry_id=reconfigure_entry.entry_id
                )
                new_data = {**reconfigure_entry.data, **data}
                new_options = {**reconfigure_entry.options, CONF_HOST: new_data.pop(CONF_HOST)}
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    title=info[CONF_NAME],
                    data=new_data,
                    options=new_options,
                )
            except KnownError as error:
                errors, placeholders = error.get_errors_and_placeholders(data_schema.schema)
                description_placeholders.update({k: str(v) for k, v in placeholders.items()})
            except Exception:  # pylint: disable=broad-except
                _LOGGER.error("Unexpected exception", exc_info=True)
                errors[CONF_BASE] = "unexpected_error"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_zeroconf(
            self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        local_name = discovery_info.hostname.rstrip(".")
        node_name = local_name[: -len(".local")]
        host = discovery_info.host
        port = discovery_info.port
        _LOGGER.debug(
            "zeroconf discovery: hostname=%r, host=%r, port=%r",
            discovery_info.hostname,
            discovery_info.host,
            discovery_info.port,
        )
        info = {CONF_HOST: host, CONF_PORT: port}
        await self.async_set_unique_id(node_name)
        self._abort_if_unique_id_configured(updates=info)
        existing_entry = self._find_entry_matching_option(CONF_HOST, lambda h: h == host)
        if existing_entry:
            _LOGGER.debug("already configured!")
            return self.async_abort(reason="already_configured")
        info[CONF_NAME] = node_name
        self._discovery_info = info
        return await self.async_step_discovery_confirm()

    @property
    def _name(self) -> str | None:
        name = self.context.get(CONF_NAME)
        return name if isinstance(name, str) else None


class WfRacOptionsFlowHandler(config_entries.OptionsFlow):
    """Base class for options handling."""

    async def async_step_init(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            data = {**user_input, CONF_HOST: self.config_entry.options[CONF_HOST]}
            return self.async_create_entry(title="", data=data)

        offset_range_validator = vol.All(vol.Coerce(float), vol.Range(min=-5.0, max=5.0))
        per_mode_offset_fields: dict[Any, Any] = {
            vol.Optional(
                key,
                description={"suggested_value": self.config_entry.options.get(key)},
            ): vol.Any(None, offset_range_validator)
            for key in (CONF_TARGET_OFFSET_COOL, CONF_TARGET_OFFSET_HEAT)
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AVAILABILITY_RETRY_LIMIT,
                        default=self.config_entry.options.get(
                            CONF_AVAILABILITY_RETRY_LIMIT, AVAILABILITY_FAILURE_LIMIT_MIN
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=AVAILABILITY_FAILURE_LIMIT_MIN)),
                    vol.Required(
                        CONF_FIRMWARE_UPDATE_CHECK,
                        default=self.config_entry.options.get(CONF_FIRMWARE_UPDATE_CHECK, False),
                    ): bool,
                    vol.Optional(
                        CONF_INDOOR_OFFSET,
                        default=self.config_entry.options.get(CONF_INDOOR_OFFSET, 0.0),
                    ): vol.All(vol.Coerce(float), vol.Range(min=-15.0, max=15.0)),
                    vol.Optional(
                        CONF_OUTDOOR_OFFSET,
                        default=self.config_entry.options.get(CONF_OUTDOOR_OFFSET, 0.0),
                    ): vol.All(vol.Coerce(float), vol.Range(min=-15.0, max=15.0)),
                    vol.Optional(
                        CONF_TARGET_OFFSET,
                        default=self.config_entry.options.get(CONF_TARGET_OFFSET, 0.0),
                    ): offset_range_validator,
                    **per_mode_offset_fields,
                },
            ),
        )


class KnownError(exceptions.HomeAssistantError):
    """Base class for errors known to this config flow."""

    error_name = "unknown_error"
    applies_to_field = CONF_BASE

    def __init__(self, *args: object, **kwargs: str) -> None:
        super().__init__(*args)
        self._extra_info = kwargs

    def get_errors_and_placeholders(
        self, schema: Any
    ) -> tuple[dict[str, str], dict[str, str]]:
        key = self.applies_to_field
        if key not in {k.schema for k in schema}:
            key = CONF_BASE
        return ({key: self.error_name}, self._extra_info or {})


class CannotConnect(KnownError):
    error_name = "cannot_connect"


class InvalidHost(KnownError):
    error_name = "invalid_host"
    applies_to_field = CONF_HOST


class HostAlreadyConfigured(KnownError):
    error_name = "host_already_configured"
    applies_to_field = CONF_HOST


class InvalidName(KnownError):
    error_name = "name_invalid"
    applies_to_field = CONF_NAME


class TooManyDevicesRegistered(KnownError):
    error_name = "too_many_devices_registered"
    applies_to_field = CONF_BASE
