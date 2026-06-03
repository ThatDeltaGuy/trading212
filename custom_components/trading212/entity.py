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
        # Position object is still available for attribute access (ticker, etc.)
        self.position = coordinator.positions[ticker]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info of the device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._ticker)},
            name=f"{self._ticker} position",
        )
