"""Support for Trading212 sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .account_sensor import ACCOUNT_WALLET_SENSORS, AccountWalletSensor
from .const import DOMAIN
from .coordinator import Trading212Coordinator
from .entity import Trading212BaseEntity


@dataclass(kw_only=True, frozen=True)
class Trading212SensorEntityDescription(SensorEntityDescription):
    """Represent the Trading212 sensor entity description.

    raw_path: if set, native_value is read by navigating this key path into
    coordinator.data[ticker] rather than from the Position object.
    """

    raw_path: tuple[str, ...] | None = None


# Keys whose values are in the instrument's native trading currency.
_INSTRUMENT_CURRENCY_KEYS = frozenset({"average_price", "current_price", "current_value"})

# Keys whose values are in the walletImpact currency (account currency after FX).
_WALLET_IMPACT_CURRENCY_KEYS = frozenset({"buy_value", "unrealized_profit_loss", "fx_impact"})

_MONETARY_KEYS = _INSTRUMENT_CURRENCY_KEYS | _WALLET_IMPACT_CURRENCY_KEYS


SENSORS: tuple[Trading212SensorEntityDescription, ...] = (
    Trading212SensorEntityDescription(
        key="average_price",
        translation_key="averagepricepaid",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="current_price",
        translation_key="currentprice",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="current_value",
        translation_key="walletvalue",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="buy_value",
        translation_key="amountinvested",
        raw_path=("walletImpact", "totalCost"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="unrealized_profit_loss",
        translation_key="unrealizedprofitloss",
        raw_path=("walletImpact", "unrealizedProfitLoss"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="fx_impact",
        translation_key="fximpact",
        raw_path=("walletImpact", "fxImpact"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="percent_change",
        translation_key="percentchange",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="quantity_available_for_trading",
        translation_key="quantityavailablefortrading",
        raw_path=("quantityAvailableForTrading",),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="initial_fill_date",
        translation_key="initialfilldate",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


def _resolve_sensor_value(
    coordinator: Trading212Coordinator,
    ticker: str,
    description: Trading212SensorEntityDescription,
) -> Any:
    """Resolve sensor value from raw coordinator data or Position object."""
    if description.raw_path is not None:
        data: Any = coordinator.data.get(ticker, {})
        for key in description.raw_path:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        return data
    return getattr(coordinator.positions[ticker], description.key, None)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Trading212 sensors from a config entry."""
    coordinator: Trading212Coordinator = hass.data[DOMAIN][config_entry.entry_id]
    account_id: str = config_entry.unique_id or ""
    currency: str = coordinator.account_data.get("currency", "")

    entities: list = [
        Trading212Sensor(coordinator, ticker, sensor)
        for ticker in coordinator.positions
        for sensor in SENSORS
        if _resolve_sensor_value(coordinator, ticker, sensor) is not None
    ]

    entities += [
        AccountWalletSensor(coordinator, account_id, currency, sensor)
        for sensor in ACCOUNT_WALLET_SENSORS
    ]

    async_add_entities(entities)


class Trading212Sensor(Trading212BaseEntity, SensorEntity):
    """Representation of a Trading212 position sensor."""

    def __init__(
        self,
        coordinator: Trading212Coordinator,
        ticker: str,
        description: Trading212SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, ticker)
        self.entity_description: Trading212SensorEntityDescription = description
        self._attr_unique_id = f"{ticker}-{description.key}"

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the appropriate currency for monetary sensors."""
        key = self.entity_description.key
        if key in _WALLET_IMPACT_CURRENCY_KEYS:
            raw = self.coordinator.data.get(self._ticker, {})
            wallet_currency = (raw.get("walletImpact") or {}).get("currency")
            return wallet_currency or self._currency or None
        if key in _INSTRUMENT_CURRENCY_KEYS:
            return self._currency or None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes depending on sensor type."""
        attrs: dict[str, Any] = {}
        key = self.entity_description.key

        # Instrument currency on instrument-priced sensors.
        if key in _INSTRUMENT_CURRENCY_KEYS and self._currency:
            attrs["instrument_currency"] = self._currency

        # Wallet value carries quantity and walletImpact summary attributes.
        if key == "current_value":
            attrs["quantity"] = self.position.quantity
            attrs["quantity_in_pies"] = self.position.pie_quantity

            raw = self.coordinator.data.get(self._ticker, {})
            wallet_impact = raw.get("walletImpact") or {}
            for src_key, attr_key in (
                ("currency", "wallet_impact_currency"),
                ("fxImpact", "wallet_impact_fx_impact"),
                ("totalCost", "wallet_impact_total_cost"),
                ("unrealizedProfitLoss", "wallet_impact_unrealized_profit_loss"),
            ):
                if src_key in wallet_impact:
                    attrs[attr_key] = wallet_impact[src_key]

        return attrs

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""
        return _resolve_sensor_value(self.coordinator, self._ticker, self.entity_description)
