"""Base class for Trading212 entities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Trading212Coordinator


class Trading212BaseEntity(CoordinatorEntity[Trading212Coordinator], Entity):
    """Base class for Trading212 entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Trading212Coordinator,
        ticker: str,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._ticker = ticker
        self.position = coordinator.positions[ticker]
        full_name, short_name, isin, instrument_type, currency = (
            coordinator.instrument_names.get(ticker, (ticker, ticker, "", "", ""))
        )
        self._device_name = f"{full_name} - {short_name}"
        self._isin = isin
        self._instrument_type = instrument_type
        self._currency = currency

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info of the device."""
        info = DeviceInfo(
            identifiers={(DOMAIN, self._ticker)},
            name=self._device_name,
            manufacturer=self._instrument_type or None,
            model=self._isin or None,
        )
        return info
