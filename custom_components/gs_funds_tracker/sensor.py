"""Sensors for GS Funds Tracker."""

from __future__ import annotations

from datetime import timedelta
import logging
import re
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed

from .const import DEFAULT_RESOURCE_URL, DEFAULT_SCAN_INTERVAL, DOMAIN, GRAPHQL_QUERY

_LOGGER = logging.getLogger(__name__)
ATTRIBUTION = "Data provided by am.gs.com"

CONF_RESOURCE_URL = "resource_url"
CONF_ENTRIES = "entries"
CONF_PV_NUMBER = "pvNumber"
CONF_SHARE_CLASS_ID = "shareClassId"
CONF_INVESTMENT_DATE = "investment_date"
CONF_VALUE_OF_INVESTMENT = "value_of_investment"
CONF_PRICE_PER_UNIT = "price_per_unit"
CONF_UNITS_ACQUIRED = "units_acquired"
CONF_CURRENCY = "currency"


ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_PV_NUMBER): cv.string,
        vol.Required(CONF_SHARE_CLASS_ID): cv.string,
        vol.Optional(CONF_INVESTMENT_DATE): cv.string,
        vol.Optional(CONF_VALUE_OF_INVESTMENT): vol.Any(vol.Coerce(float), None),
        vol.Required(CONF_PRICE_PER_UNIT): vol.Coerce(float),
        vol.Optional(CONF_UNITS_ACQUIRED): vol.Any(vol.Coerce(float), None),
        vol.Optional(CONF_CURRENCY): vol.Any(cv.string, None),
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_RESOURCE_URL, default=DEFAULT_RESOURCE_URL): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
        vol.Required(CONF_ENTRIES): vol.All(cv.ensure_list, [ENTRY_SCHEMA]),
    }
)


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_") or "fund"


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities: AddEntitiesCallback, discovery_info=None
):
    """Set up GS Funds Tracker sensors via YAML."""
    resource_url: str = config[CONF_RESOURCE_URL]
    scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    entries: List[dict] = config.get(CONF_ENTRIES, [])
    group_stats = calculate_group_stats(entries)

    session = aiohttp_client.async_get_clientsession(hass)

    sensors: List[SensorEntity] = []
    for entry in entries:
        coordinator = FundCoordinator(
            hass,
            session,
            entry=entry,
            resource_url=resource_url,
            group_info=group_stats.get(_group_key(entry)),
            update_interval=timedelta(seconds=scan_interval),
        )
        await coordinator.async_config_entry_first_refresh()

        sensors.append(NavSensor(coordinator))
        sensors.append(ProfitSensor(coordinator))
        sensors.append(ReturnSensor(coordinator))

    async_add_entities(sensors, update_before_add=False)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up GS Funds Tracker sensors from config entry (UI)."""
    data = entry.data
    options = entry.options or {}
    resource_url: str = options.get(CONF_RESOURCE_URL, data.get(CONF_RESOURCE_URL, DEFAULT_RESOURCE_URL))
    scan_interval = options.get(CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    entries: List[dict] = options.get(CONF_ENTRIES, data.get(CONF_ENTRIES, []))
    group_stats = calculate_group_stats(entries)

    session = aiohttp_client.async_get_clientsession(hass)

    sensors: List[SensorEntity] = []
    for fund_entry in entries:
        coordinator = FundCoordinator(
            hass,
            session,
            entry=fund_entry,
            resource_url=resource_url,
            group_info=group_stats.get(_group_key(fund_entry)),
            update_interval=timedelta(seconds=scan_interval),
        )
        await coordinator.async_config_entry_first_refresh()

        sensors.append(NavSensor(coordinator))
        sensors.append(ProfitSensor(coordinator))
        sensors.append(ReturnSensor(coordinator))

    async_add_entities(sensors, update_before_add=False)


def _group_key(entry: dict) -> Optional[str]:
    scid = entry.get(CONF_SHARE_CLASS_ID)
    pv = entry.get(CONF_PV_NUMBER)
    if not scid or not pv:
        return None
    return f"{pv}:{scid}"


def calculate_group_stats(entries: List[dict]) -> Dict[str, Dict[str, float]]:
    """Compute weighted average price and total units per (pvNumber, shareClassId)."""
    groups: Dict[str, Dict[str, float]] = {}
    for entry in entries:
        key = _group_key(entry)
        if not key:
            continue
        price = float(entry.get(CONF_PRICE_PER_UNIT, 0) or 0)
        units = entry.get(CONF_UNITS_ACQUIRED)
        if units is None:
            total = entry.get(CONF_VALUE_OF_INVESTMENT)
            units = (float(total) / price) if total and price else 0.0
        units = float(units or 0)
        group = groups.setdefault(key, {"weighted_sum": 0.0, "total_units": 0.0})
        group["weighted_sum"] += price * units
        group["total_units"] += units
    for key, group in groups.items():
        total_units = group["total_units"]
        group["avg_price"] = round(group["weighted_sum"] / total_units, 4) if total_units else 0.0
    return groups


def _format_units(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"{value:.3f}"


class FundCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator fetching fund data."""

    def __init__(
        self,
        hass,
        session,
        entry: dict,
        resource_url: str,
        group_info: Optional[Dict[str, Any]],
        update_interval: timedelta,
    ) -> None:
        self._entry = entry
        self._resource_url = resource_url
        self._session = session
        self._group_info = group_info or {}
        self.entry_slug = slugify(entry.get(CONF_NAME) or entry.get(CONF_SHARE_CLASS_ID, "fund"))
        name = f"GS Fund {self.entry_slug}"

        super().__init__(hass, _LOGGER, name=name, update_interval=update_interval)

    async def _async_update_data(self) -> Dict[str, Any]:
        payload = {
            "operationName": "getFundsDetail",
            "variables": {
                "fundDetailRequest": {
                    "country": "ro",
                    "language": "ro",
                    "audience": "individual",
                    "pvNumber": self._entry[CONF_PV_NUMBER],
                    "shareClassId": self._entry[CONF_SHARE_CLASS_ID],
                }
            },
            "query": GRAPHQL_QUERY,
        }

        try:
            async with self._session.post(
                self._resource_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"HTTP {resp.status}")
                data = await resp.json()
        except Exception as exc:
            raise UpdateFailed(f"Request failed: {exc}") from exc

        fund_detail = (data.get("data") or {}).get("fundsDetail")
        if not fund_detail:
            raise UpdateFailed("No fund detail in response")

        quick_stats = fund_detail.get("quickStats") or []
        nav_stat = next((item for item in quick_stats if item.get("label") == "netAssetValue"), None)
        if not nav_stat or nav_stat.get("value") is None:
            raise UpdateFailed("NAV not found")

        nav = float(nav_stat.get("value"))
        acquisition_price = float(self._entry.get(CONF_PRICE_PER_UNIT, 0) or 0)
        units = self._entry.get(CONF_UNITS_ACQUIRED)
        if units is None:
            total = self._entry.get(CONF_VALUE_OF_INVESTMENT)
            units = (float(total) / acquisition_price) if total and acquisition_price else 0.0

        group_avg_price = self._group_info.get("avg_price")
        group_units = self._group_info.get("total_units")
        effective_price = group_avg_price if group_avg_price is not None else acquisition_price
        effective_units = group_units if group_units is not None else units

        # Profit per entry uses that entry's units; return_pct uses the averaged acquisition price.
        profit = (nav - effective_price) * units if effective_price else 0.0
        return_pct = ((nav / effective_price) - 1) * 100 if effective_price else 0.0

        fund_name = self._entry.get(CONF_NAME) or fund_detail.get("fundName") or "Fund"
        share_class = fund_detail.get("id") or self._entry.get(CONF_SHARE_CLASS_ID)

        return {
            "fund_name": fund_name,
            "share_class_id": share_class,
            "pv_number": self._entry.get(CONF_PV_NUMBER),
            "currency": nav_stat.get("currency") or self._entry.get(CONF_CURRENCY),
            "as_at_date": nav_stat.get("asAtDate"),
            "nav": nav,
            "up_down_value": nav_stat.get("upDownValue"),
            "up_down_pct": nav_stat.get("upDownPctValue"),
            "acquisition_price": effective_price,
            "entry_price": acquisition_price,
            "entry_units": _format_units(units),
            "group_avg_price": group_avg_price,
            "group_total_units": _format_units(group_units),
            "units": _format_units(effective_units),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
            "investment_date": self._entry.get(CONF_INVESTMENT_DATE),
            "value_of_investment": self._entry.get(CONF_VALUE_OF_INVESTMENT),
            "sc_base_currency": fund_detail.get("scBaseCurrency") or self._entry.get(CONF_CURRENCY),
            "units_aquired": units,
        }


class BaseFundSensor(CoordinatorEntity[FundCoordinator], SensorEntity):
    """Base sensor shared logic."""

    _attr_should_poll = False

    def __init__(self, coordinator: FundCoordinator) -> None:
        super().__init__(coordinator)
        self._entry_slug = coordinator.entry_slug

    @property
    def device_info(self) -> DeviceInfo | None:
        data = self.coordinator.data
        name = f"{data.get('fund_name')} - {data.get('share_class_id')}"
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_slug)},
            name=name,
            manufacturer="Goldman Sachs",
            model=str(data.get("share_class_id")),
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data = self.coordinator.data
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "fund_name": data.get("fund_name"),
            "share_class_id": data.get("share_class_id"),
            "pv_number": data.get("pv_number"),
            "currency": data.get("currency"),
            "as_at_date": data.get("as_at_date"),
            "investment_date": data.get("investment_date"),
            "value_of_investment": data.get("value_of_investment"),
            "sc_base_currency": data.get("sc_base_currency"),
            "up_down_value": data.get("up_down_value"),
            "up_down_pct": data.get("up_down_pct"),
            "entry_price": data.get("entry_price"),
            "entry_units": data.get("entry_units"),
            "group_avg_price": data.get("group_avg_price"),
            "group_total_units": data.get("group_total_units"),
        }


class NavSensor(BaseFundSensor):
    """Current NAV sensor."""

    @property
    def name(self) -> str:
        data = self.coordinator.data
        return f"{data.get('fund_name')} - {data.get('share_class_id')}"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_slug}_nav"

    @property
    def native_value(self):
        return self.coordinator.data.get("nav")

    @property
    def native_unit_of_measurement(self):
        return self.coordinator.data.get("currency")

    @property
    def device_class(self):
        return "monetary"


class ProfitSensor(BaseFundSensor):
    """Absolute profit sensor."""

    @property
    def name(self) -> str:
        data = self.coordinator.data
        return f"{data.get('fund_name')} Profit Net"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_slug}_profit"

    @property
    def native_value(self):
        return self.coordinator.data.get("profit")

    @property
    def native_unit_of_measurement(self):
        return self.coordinator.data.get("currency")


class ReturnSensor(BaseFundSensor):
    """Percentage return sensor."""

    @property
    def name(self) -> str:
        data = self.coordinator.data
        return f"{data.get('fund_name')} Randament"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_slug}_return_pct"

    @property
    def native_value(self):
        return self.coordinator.data.get("return_pct")

    @property
    def native_unit_of_measurement(self):
        return "%"
