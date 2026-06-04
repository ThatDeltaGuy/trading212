"""Account Wallet sensors for the Trading212 integration.

These sensors represent account-level data from equity/account/summary
and are grouped under a single 'Account Wallet' device.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Trading212Coordinator


@dataclass(kw_only=True, frozen=True)
class AccountWalletSensorDescription(SensorEntityDescription):
    """Sensor description for account wallet sensors.

    path: tuple of keys to navigate the account summary response dict,
    e.g. ("cash", "availableToTrade") or ("totalValue",).
    """

    path: tuple[str, ...] = ()


ACCOUNT_WALLET_SENSORS: tuple[AccountWalletSensorDescription, ...] = (
    AccountWalletSensorDescription(
        key="available_to_trade",
        translation_key="mainpot",
        path=("cash", "availableToTrade"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AccountWalletSensorDescription(
        key="cash_in_pies",
        translation_key="cashinpies",
        path=("cash", "inPies"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AccountWalletSensorDescription(
        key="reserved_for_orders",
        translation_key="reservedfororders",
        path=("cash", "reservedForOrders"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AccountWalletSensorDescription(
        key="investments_current_value",
        translation_key="totalinvestmentvalue",
        path=("investments", "currentValue"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AccountWalletSensorDescription(
        key="realized_profit_loss",
        translation_key="realizedprofitloss",
        path=("investments", "realizedProfitLoss"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AccountWalletSensorDescription(
        key="total_cost",
        translation_key="totalinvested",
        path=("investments", "totalCost"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AccountWalletSensorDescription(
        key="unrealized_profit_loss",
        translation_key="unrealizedprofitloss",
        path=("investments", "unrealizedProfitLoss"),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
)


class AccountWalletSensor(CoordinatorEntity[Trading212Coordinator], SensorEntity):
    """Sensor for account-level Trading212 data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Trading212Coordinator,
        account_id: str,
        currency: str,
        description: AccountWalletSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._account_id = account_id
        self._currency = currency
        self.entity_description: AccountWalletSensorDescription = description
        self._attr_unique_id = f"{account_id}_wallet_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}_wallet")},
            name="Account Wallet",
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        """All account wallet sensors are monetary values in the account currency."""
        return self._currency or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the account currency as an attribute."""
        return {"currency": self._currency} if self._currency else {}

    @property
    def native_value(self) -> StateType:
        """Navigate the path into account_data to extract the sensor value."""
        data: Any = self.coordinator.account_data
        for key in self.entity_description.path:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        return data
