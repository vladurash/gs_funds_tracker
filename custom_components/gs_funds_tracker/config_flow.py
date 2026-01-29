"""Config flow for GS Funds Tracker."""

from __future__ import annotations

from typing import Any, Dict, List

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL

from .const import (
    DEFAULT_RESOURCE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .sensor import (
    CONF_CURRENCY,
    CONF_ENTRIES,
    CONF_INVESTMENT_DATE,
    CONF_PRICE_PER_UNIT,
    CONF_PV_NUMBER,
    CONF_RESOURCE_URL,
    CONF_SHARE_CLASS_ID,
    CONF_UNITS_ACQUIRED,
    CONF_VALUE_OF_INVESTMENT,
    ENTRY_SCHEMA,
)


class GSFundsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._resource_url: str = DEFAULT_RESOURCE_URL
        self._scan_interval: int = DEFAULT_SCAN_INTERVAL
        self._entries: List[Dict[str, Any]] = []
        self._editing_index: int | None = None

    async def async_step_user(self, user_input=None):
        """First step: global settings."""
        if user_input is not None:
            self._resource_url = user_input.get(CONF_RESOURCE_URL, DEFAULT_RESOURCE_URL)
            self._scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            return await self.async_step_entry()

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_RESOURCE_URL, default=self._resource_url): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.All(
                    int, vol.Clamp(min=60, max=86400)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_entry(self, user_input=None):
        """Collect one fund entry."""
        errors = {}
        if user_input is not None:
            entry_errors = _validate_entry(user_input)
            if entry_errors:
                errors = entry_errors
            else:
                self._entries.append(user_input)
                return await self.async_step_more()

        data_schema = vol.Schema(ENTRY_SCHEMA.schema)
        return self.async_show_form(step_id="entry", data_schema=data_schema, errors=errors)

    async def async_step_more(self, user_input=None):
        """Ask if user wants to add another entry or finish."""
        if user_input is not None:
            if user_input.get("add_another"):
                return await self.async_step_entry()
            if not self._entries:
                # must have at least one entry
                return await self.async_step_entry()
            return self._create_entry()

        return self.async_show_form(
            step_id="more",
            data_schema=vol.Schema({vol.Required("add_another", default=False): bool}),
        )

    def _create_entry(self):
        return self.async_create_entry(
            title="GS Funds Tracker",
            data={},  # keep entry data in options
            options={
                CONF_RESOURCE_URL: self._resource_url,
                CONF_SCAN_INTERVAL: self._scan_interval,
                CONF_ENTRIES: self._entries,
            },
        )

    async def async_step_import(self, user_input=None):
        """Import from YAML."""
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(config_entry):
        return GSFundsOptionsFlowHandler(config_entry)


class GSFundsOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._resource_url = config_entry.options.get(
            CONF_RESOURCE_URL, config_entry.data.get(CONF_RESOURCE_URL, DEFAULT_RESOURCE_URL)
        )
        self._scan_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL, config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._entries: List[Dict[str, Any]] = config_entry.options.get(
            CONF_ENTRIES, config_entry.data.get(CONF_ENTRIES, [])
        )
        self._editing_index: int | None = None

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self._resource_url = user_input.get(CONF_RESOURCE_URL, self._resource_url)
            self._scan_interval = user_input.get(CONF_SCAN_INTERVAL, self._scan_interval)
            return await self.async_step_entries_menu()

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_RESOURCE_URL, default=self._resource_url): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.All(
                    int, vol.Clamp(min=60, max=86400)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)

    async def async_step_entries_menu(self, user_input=None):
        """Choose add/edit/delete or finish."""
        actions = ["add", "finish"]
        if self._entries:
            actions = ["add", "edit", "delete", "finish"]

        if user_input is not None:
            action = user_input["action"]
            index = user_input.get("entry")
            if action == "add":
                return await self.async_step_entry_add()
            if action == "edit" and index is not None and index < len(self._entries):
                self._editing_index = index
                return await self.async_step_entry_edit()
            if action == "delete" and index is not None and index < len(self._entries):
                self._entries.pop(index)
                return await self.async_step_entries_menu()
            if action == "finish":
                if not self._entries:
                    return await self.async_step_entry_add()
                return self._create_entry()

        schema: Dict[Any, Any] = {vol.Required("action"): vol.In(actions)}
        if self._entries:
            choices = {i: f"{i}: {e.get(CONF_NAME) or e.get(CONF_SHARE_CLASS_ID)}" for i, e in enumerate(self._entries)}
            first_key = next(iter(choices))
            schema[vol.Optional("entry", default=first_key)] = vol.In(choices)
        return self.async_show_form(step_id="entries_menu", data_schema=vol.Schema(schema))

    async def async_step_entry_add(self, user_input=None):
        """Add a new entry."""
        return await self._entry_form(user_input, edit_index=None, step_id="entry_add")

    async def async_step_entry_edit(self, user_input=None):
        """Edit an existing entry."""
        return await self._entry_form(user_input, edit_index=self._editing_index, step_id="entry_edit")

    def _create_entry(self):
        return self.async_create_entry(
            title="GS Funds Tracker",
            data={
                CONF_RESOURCE_URL: self._resource_url,
                CONF_SCAN_INTERVAL: self._scan_interval,
                CONF_ENTRIES: self._entries,
            },
        )

    async def _entry_form(self, user_input, edit_index: int | None, step_id: str):
        errors = {}
        defaults = self._entries[edit_index] if edit_index is not None else None

        if user_input is not None:
            entry_errors = _validate_entry(user_input)
            if entry_errors:
                errors = entry_errors
            else:
                normalized = _normalize_optional_numbers(user_input)
                if edit_index is None:
                    self._entries.append(normalized)
                else:
                    self._entries[edit_index] = normalized
                return await self.async_step_entries_menu()

        data_schema = _entry_schema_with_defaults(defaults)
        return self.async_show_form(step_id=step_id, data_schema=data_schema, errors=errors)


def _validate_entry(entry: Dict[str, Any]) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    try:
        ENTRY_SCHEMA(entry)
    except vol.Invalid:
        errors["base"] = "invalid_entry"
        return errors
    if not entry.get(CONF_PRICE_PER_UNIT):
        errors["price_per_unit"] = "required"
    return errors


def _normalize_optional_numbers(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(entry)
    for key in (CONF_VALUE_OF_INVESTMENT, CONF_UNITS_ACQUIRED):
        if key not in normalized or normalized[key] == "" or normalized[key] is vol.UNDEFINED:
            normalized[key] = None
    if normalized.get(CONF_INVESTMENT_DATE) == "":
        normalized[CONF_INVESTMENT_DATE] = None
    if normalized.get(CONF_CURRENCY) == "":
        normalized[CONF_CURRENCY] = None
    return normalized


def _entry_schema_with_defaults(defaults: Dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
            vol.Required(CONF_PV_NUMBER, default=defaults.get(CONF_PV_NUMBER, "")): str,
            vol.Required(CONF_SHARE_CLASS_ID, default=defaults.get(CONF_SHARE_CLASS_ID, "")): str,
            vol.Optional(CONF_INVESTMENT_DATE, default=defaults.get(CONF_INVESTMENT_DATE, "")): str,
            vol.Optional(CONF_VALUE_OF_INVESTMENT, default=defaults.get(CONF_VALUE_OF_INVESTMENT, vol.UNDEFINED)): vol.Coerce(
                float
            ),
            vol.Required(CONF_PRICE_PER_UNIT, default=defaults.get(CONF_PRICE_PER_UNIT, 0.0)): vol.Coerce(float),
            vol.Optional(CONF_UNITS_ACQUIRED, default=defaults.get(CONF_UNITS_ACQUIRED, vol.UNDEFINED)): vol.Coerce(float),
            vol.Optional(CONF_CURRENCY, default=defaults.get(CONF_CURRENCY, "")): str,
        }
    )
