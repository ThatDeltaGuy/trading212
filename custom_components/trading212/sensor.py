"""Support for Trading212 sensors."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .coordinator import Trading212Coordinator
from .entity import Trading212BaseEntity


@dataclass(kw_only=True, frozen=True)
class Trading212SensorEntityDescription(SensorEntityDescription):
    """Represent the Trading212 entity description."""


SENSORS: tuple[Trading212SensorEntityDescription, ...] = (
    Trading212SensorEntityDescription(
        key="average_price",
        translation_key="averageprice",
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
        key="quantity",
        translation_key="quantity",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Trading212SensorEntityDescription(
        key="current_value",
        translation_key="walletvalue",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="buy_value",
        translation_key="invested",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    Trading212SensorEntityDescription(
        key="percent_change",
        translation_key="percentchange",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Trading212 sensors from config entry."""

    coordinator: Trading212Coordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        Trading212Sensor(coordinator, ticker, sensor)
        for ticker in coordinator.positions
        for sensor in SENSORS
        if getattr(coordinator.positions[ticker], sensor.key, None) is not None
    )


class Trading212Sensor(Trading212BaseEntity, SensorEntity):
    """Representation of an Trading212 sensor."""

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
        """Return the unit of measurement from the instrument's trading currency."""
        if self.entity_description.key in (
            "average_price", "current_price", "current_value", "buy_value"
        ):
            return self._currency or None
        return None

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""

        return getattr(self.position, self.entity_description.key, None)
