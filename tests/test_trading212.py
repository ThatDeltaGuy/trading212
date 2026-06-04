"""Tests for the Trading212 custom integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from pytrading212api.exceptions import (
    Trading212AttemptsExceeded,
    Trading212BadApiKey,
    Trading212Error,
    Trading212Limited,
    Trading212TimeOut,
)
from pytrading212api.position import Position


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

RAW_POSITION_1: dict[str, Any] = {
    "ticker": "AAPL_US_EQ",
    "quantity": 10.0,
    "averagePrice": 150.00,
    "currentPrice": 175.00,
    "ppl": 250.00,
    "fxPpl": 0.0,
    "initialFillDate": "2024-01-15T10:30:00",
    "frontend": "WC4",
    "maxBuy": 100.0,
    "maxSell": 10.0,
    "pieQuantity": 0,
}

RAW_POSITION_2: dict[str, Any] = {
    "ticker": "MSFT_US_EQ",
    "quantity": 5.0,
    "averagePrice": 300.00,
    "currentPrice": 320.00,
    "ppl": 100.00,
    "fxPpl": 0.0,
    "initialFillDate": "2024-02-01T09:00:00",
    "frontend": "WC4",
    "maxBuy": 50.0,
    "maxSell": 5.0,
    "pieQuantity": 0,
}

RAW_POSITION_UPDATED: dict[str, Any] = {
    **RAW_POSITION_1,
    "currentPrice": 180.00,
    "ppl": 300.00,
}

INSTRUMENT_NAMES: dict[str, tuple[str, str, str, str, str]] = {
    "AAPL_US_EQ": ("Apple Inc", "AAPL", "US0378331005", "STOCK", "USD"),
    "MSFT_US_EQ": ("Microsoft Corp", "MSFT", "US5949181045", "STOCK", "USD"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_api(return_value: list[dict] | None = None) -> MagicMock:
    """Return a mock Trading212API with get_positions pre-configured."""
    api = MagicMock()
    api.get_positions = AsyncMock(
        return_value=return_value if return_value is not None else [RAW_POSITION_1]
    )
    return api


def make_mock_hass() -> MagicMock:
    hass = MagicMock()
    hass.loop = asyncio.get_event_loop()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    return hass


def make_mock_config_entry(scan_interval: int = 30) -> MagicMock:
    entry = MagicMock()
    entry.data = {"id": "test-account-id"}
    entry.options = {"scan_interval": scan_interval}
    return entry


def make_position(api: MagicMock, raw: dict) -> Position:
    return Position(api, raw)


def make_coordinator(raw_positions=None, interval=30, api_exception=None, instrument_names=None):
    """Build a Trading212Coordinator with DataUpdateCoordinator.__init__ patched out."""
    from custom_components.trading212.coordinator import Trading212Coordinator

    if raw_positions is None:
        raw_positions = [RAW_POSITION_1]
    if instrument_names is None:
        instrument_names = INSTRUMENT_NAMES

    api = make_mock_api(raw_positions)
    if api_exception is not None:
        api.get_positions = AsyncMock(side_effect=api_exception)

    positions = [make_position(api, r) for r in raw_positions]
    hass = make_mock_hass()
    entry = make_mock_config_entry()

    with patch(
        "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coord = Trading212Coordinator(hass, api, positions, instrument_names, interval, entry)

    coord.hass = hass
    coord.logger = MagicMock()
    coord.config_entry = entry
    coord._base_interval = timedelta(seconds=max(interval, 10))
    coord.update_interval = timedelta(seconds=max(interval, 10))
    return coord


# ---------------------------------------------------------------------------
# Coordinator: __init__ and interval clamping
# ---------------------------------------------------------------------------

class TestCoordinatorInit:
    def test_positions_keyed_by_ticker(self):
        from custom_components.trading212.coordinator import Trading212Coordinator

        api = make_mock_api([RAW_POSITION_1, RAW_POSITION_2])
        positions = [make_position(api, RAW_POSITION_1), make_position(api, RAW_POSITION_2)]

        with patch(
            "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = Trading212Coordinator(
                make_mock_hass(), api, positions, INSTRUMENT_NAMES, 30, make_mock_config_entry()
            )

        assert "AAPL_US_EQ" in coord.positions
        assert "MSFT_US_EQ" in coord.positions
        assert coord.positions["AAPL_US_EQ"].ticker == "AAPL_US_EQ"

    def test_instrument_names_stored_on_coordinator(self):
        from custom_components.trading212.coordinator import Trading212Coordinator

        api = make_mock_api()
        positions = [make_position(api, RAW_POSITION_1)]

        with patch(
            "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = Trading212Coordinator(
                make_mock_hass(), api, positions, INSTRUMENT_NAMES, 30, make_mock_config_entry()
            )

        assert coord.instrument_names["AAPL_US_EQ"] == ("Apple Inc", "AAPL", "US0378331005", "STOCK", "USD")

    def test_interval_below_minimum_is_clamped(self):
        from custom_components.trading212.coordinator import Trading212Coordinator, _MIN_INTERVAL

        captured = {}

        def capturing_init(self, hass, logger, *, name, update_interval=None, **kwargs):
            captured["update_interval"] = update_interval

        api = make_mock_api()
        positions = [make_position(api, RAW_POSITION_1)]

        with patch(
            "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
            capturing_init,
        ):
            Trading212Coordinator(
                make_mock_hass(), api, positions, INSTRUMENT_NAMES, 1, make_mock_config_entry()
            )

        assert captured["update_interval"] >= _MIN_INTERVAL

    def test_interval_above_minimum_is_preserved(self):
        from custom_components.trading212.coordinator import Trading212Coordinator

        captured = {}

        def capturing_init(self, hass, logger, *, name, update_interval=None, **kwargs):
            captured["update_interval"] = update_interval

        api = make_mock_api()
        positions = [make_position(api, RAW_POSITION_1)]

        with patch(
            "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
            capturing_init,
        ):
            Trading212Coordinator(
                make_mock_hass(), api, positions, INSTRUMENT_NAMES, 60, make_mock_config_entry()
            )

        assert captured["update_interval"] == timedelta(seconds=60)

    def test_api_stored_on_coordinator(self):
        from custom_components.trading212.coordinator import Trading212Coordinator

        api = make_mock_api()
        positions = [make_position(api, RAW_POSITION_1)]

        with patch(
            "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = Trading212Coordinator(
                make_mock_hass(), api, positions, INSTRUMENT_NAMES, 30, make_mock_config_entry()
            )

        assert coord.api is api


# ---------------------------------------------------------------------------
# Coordinator: _async_update_data — happy path
# ---------------------------------------------------------------------------

class TestCoordinatorUpdateData:
    @pytest.mark.asyncio
    async def test_returns_dict_keyed_by_ticker(self):
        coord = make_coordinator([RAW_POSITION_1, RAW_POSITION_2])
        result = await coord._async_update_data()
        assert set(result.keys()) == {"AAPL_US_EQ", "MSFT_US_EQ"}

    @pytest.mark.asyncio
    async def test_result_contains_raw_api_data(self):
        coord = make_coordinator([RAW_POSITION_1])
        result = await coord._async_update_data()
        assert result["AAPL_US_EQ"]["currentPrice"] == 175.00

    @pytest.mark.asyncio
    async def test_updates_position_in_place(self):
        coord = make_coordinator([RAW_POSITION_1])
        assert coord.positions["AAPL_US_EQ"].current_price == 175.00
        coord.api.get_positions = AsyncMock(return_value=[RAW_POSITION_UPDATED])
        await coord._async_update_data()
        assert coord.positions["AAPL_US_EQ"].current_price == 180.00

    @pytest.mark.asyncio
    async def test_position_object_identity_preserved_on_update(self):
        coord = make_coordinator([RAW_POSITION_1])
        original = coord.positions["AAPL_US_EQ"]
        coord.api.get_positions = AsyncMock(return_value=[RAW_POSITION_UPDATED])
        await coord._async_update_data()
        assert coord.positions["AAPL_US_EQ"] is original

    @pytest.mark.asyncio
    async def test_new_position_added_dynamically(self):
        coord = make_coordinator([RAW_POSITION_1])
        assert "MSFT_US_EQ" not in coord.positions
        coord.api.get_positions = AsyncMock(return_value=[RAW_POSITION_1, RAW_POSITION_2])
        await coord._async_update_data()
        assert "MSFT_US_EQ" in coord.positions

    @pytest.mark.asyncio
    async def test_makes_exactly_one_api_call(self):
        coord = make_coordinator([RAW_POSITION_1, RAW_POSITION_2])
        await coord._async_update_data()
        coord.api.get_positions.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_restores_base_interval_after_backoff(self):
        from custom_components.trading212.coordinator import _RATE_LIMIT_BACKOFF
        coord = make_coordinator([RAW_POSITION_1])
        coord.update_interval = _RATE_LIMIT_BACKOFF
        await coord._async_update_data()
        assert coord.update_interval == coord._base_interval

    @pytest.mark.asyncio
    async def test_interval_unchanged_on_normal_successful_fetch(self):
        coord = make_coordinator([RAW_POSITION_1])
        original_interval = coord.update_interval
        await coord._async_update_data()
        assert coord.update_interval == original_interval


# ---------------------------------------------------------------------------
# Coordinator: _async_update_data — error handling
# ---------------------------------------------------------------------------

class TestCoordinatorErrorHandling:
    @pytest.mark.asyncio
    async def test_bad_api_key_raises_config_entry_auth_failed(self):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        coord = make_coordinator(api_exception=Trading212BadApiKey("bad key"))
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_timeout_raises_update_failed(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coord = make_coordinator(api_exception=Trading212TimeOut("timeout"))
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_generic_error_raises_update_failed(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coord = make_coordinator(api_exception=Trading212Error("error"))
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_rate_limited_raises_update_failed(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coord = make_coordinator(api_exception=Trading212Limited(60))
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_attempts_exceeded_raises_update_failed(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coord = make_coordinator(api_exception=Trading212AttemptsExceeded("too many"))
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_attempts_exceeded_sets_backoff_interval(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        from custom_components.trading212.coordinator import _RATE_LIMIT_BACKOFF
        coord = make_coordinator(api_exception=Trading212AttemptsExceeded("too many"))
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        assert coord.update_interval == _RATE_LIMIT_BACKOFF

    @pytest.mark.asyncio
    async def test_backoff_interval_persists_until_next_success(self):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        from custom_components.trading212.coordinator import _RATE_LIMIT_BACKOFF
        coord = make_coordinator(api_exception=Trading212AttemptsExceeded("too many"))
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        assert coord.update_interval != coord._base_interval

    @pytest.mark.asyncio
    async def test_bad_api_key_does_not_alter_interval(self):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        coord = make_coordinator(api_exception=Trading212BadApiKey("bad key"))
        original = coord.update_interval
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()
        assert coord.update_interval == original


# ---------------------------------------------------------------------------
# Position data model
# ---------------------------------------------------------------------------

class TestPositionModel:
    def _make(self, raw: dict) -> Position:
        return Position(make_mock_api(), raw)

    def test_ticker(self):
        assert self._make(RAW_POSITION_1).ticker == "AAPL_US_EQ"

    def test_quantity(self):
        assert self._make(RAW_POSITION_1).quantity == pytest.approx(10.0)

    def test_average_price(self):
        assert self._make(RAW_POSITION_1).average_price == pytest.approx(150.00)

    def test_current_price(self):
        assert self._make(RAW_POSITION_1).current_price == pytest.approx(175.00)

    def test_computed_buy_value(self):
        assert self._make(RAW_POSITION_1).buy_value == pytest.approx(1500.00)

    def test_computed_current_value(self):
        assert self._make(RAW_POSITION_1).current_value == pytest.approx(1750.00)

    def test_percent_change_positive(self):
        assert self._make(RAW_POSITION_1).percent_change == pytest.approx(
            round(250.0 / 1500.0 * 100, 2)
        )

    def test_percent_change_zero_buy_value_does_not_raise(self):
        raw = {**RAW_POSITION_1, "quantity": 0.0, "averagePrice": 0.0}
        assert self._make(raw).percent_change == 0.0

    def test_update_position_mutates_current_price(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        assert p.current_price == 180.00

    def test_update_position_recalculates_current_value(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        assert p.current_value == pytest.approx(1800.00)

    def test_update_position_buy_value_unchanged(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        assert p.buy_value == pytest.approx(1500.00)

    def test_update_position_recalculates_percent_change(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        assert p.percent_change == pytest.approx(round(300.0 / 1500.0 * 100, 2))


# ---------------------------------------------------------------------------
# Entity base class
# ---------------------------------------------------------------------------

class TestBaseEntity:
    def _make_entity(self, raw=None, instrument_names=None):
        from custom_components.trading212.entity import Trading212BaseEntity
        if raw is None:
            raw = RAW_POSITION_1
        if instrument_names is None:
            instrument_names = INSTRUMENT_NAMES

        coord = make_coordinator([raw], instrument_names=instrument_names)
        coord.data = {raw["ticker"]: raw}
        coord._listeners = {}
        coord.last_update_success = True

        with patch(
            "custom_components.trading212.entity.CoordinatorEntity.__init__",
            return_value=None,
        ):
            entity = Trading212BaseEntity.__new__(Trading212BaseEntity)
            entity.coordinator = coord
            entity._ticker = raw["ticker"]
            entity.position = coord.positions[raw["ticker"]]
            full_name, short_name, isin, instrument_type, currency = (
                coord.instrument_names.get(raw["ticker"], (raw["ticker"], raw["ticker"], "", "", ""))
            )
            entity._device_name = f"{full_name} - {short_name}"
            entity._isin = isin
            entity._instrument_type = instrument_type
            entity._currency = currency

        return entity, coord

    def test_device_info_identifier_contains_ticker(self):
        entity, _ = self._make_entity()
        assert ("trading212", "AAPL_US_EQ") in entity.device_info["identifiers"]

    def test_device_info_name_uses_full_and_short_name(self):
        entity, _ = self._make_entity()
        assert entity.device_info["name"] == "Apple Inc - AAPL"

    def test_device_info_manufacturer_is_instrument_type(self):
        entity, _ = self._make_entity()
        assert entity.device_info["manufacturer"] == "STOCK"

    def test_device_info_model_is_isin(self):
        entity, _ = self._make_entity()
        assert entity.device_info["model"] == "US0378331005"

    def test_device_info_manufacturer_none_when_unknown(self):
        entity, _ = self._make_entity(instrument_names={})
        assert entity.device_info.get("manufacturer") is None

    def test_device_info_model_none_when_unknown(self):
        entity, _ = self._make_entity(instrument_names={})
        assert entity.device_info.get("model") is None

    def test_device_info_name_falls_back_to_ticker_when_unknown(self):
        entity, _ = self._make_entity(instrument_names={})
        assert entity.device_info["name"] == "AAPL_US_EQ - AAPL_US_EQ"

    def test_position_attribute_is_same_object_as_coordinator(self):
        entity, coord = self._make_entity()
        assert entity.position is coord.positions["AAPL_US_EQ"]

    def test_position_reflects_coordinator_update(self):
        entity, coord = self._make_entity()
        coord.positions["AAPL_US_EQ"]._update_position(RAW_POSITION_UPDATED)
        assert entity.position.current_price == pytest.approx(180.00)


# ---------------------------------------------------------------------------
# Sensor: native_value
# ---------------------------------------------------------------------------

class TestSensorNativeValue:
    def _make_sensor(self, key: str, raw=None):
        from custom_components.trading212.sensor import Trading212Sensor, SENSORS
        if raw is None:
            raw = RAW_POSITION_1

        coord = make_coordinator([raw])
        coord.data = {raw["ticker"]: raw}
        coord._listeners = {}
        coord.last_update_success = True

        description = next(s for s in SENSORS if s.key == key)

        with patch(
            "custom_components.trading212.entity.CoordinatorEntity.__init__",
            return_value=None,
        ):
            sensor = Trading212Sensor.__new__(Trading212Sensor)
            sensor.coordinator = coord
            sensor._ticker = raw["ticker"]
            sensor.position = coord.positions[raw["ticker"]]
            sensor.entity_description = description
            sensor._attr_unique_id = f"{raw['ticker']}-{key}"

        return sensor

    def test_current_price(self):
        assert self._make_sensor("current_price").native_value == pytest.approx(175.00)

    def test_average_price(self):
        assert self._make_sensor("average_price").native_value == pytest.approx(150.00)

    def test_current_value(self):
        assert self._make_sensor("current_value").native_value == pytest.approx(1750.00)

    def test_buy_value(self):
        assert self._make_sensor("buy_value").native_value == pytest.approx(1500.00)

    def test_percent_change(self):
        assert self._make_sensor("percent_change").native_value == pytest.approx(
            round(250.0 / 1500.0 * 100, 2)
        )

    def test_unique_id_format(self):
        assert self._make_sensor("current_price")._attr_unique_id == "AAPL_US_EQ-current_price"

    def test_native_value_reflects_position_update(self):
        sensor = self._make_sensor("current_price")
        sensor.position._update_position(RAW_POSITION_UPDATED)
        assert sensor.native_value == pytest.approx(180.00)


# ---------------------------------------------------------------------------
# Sensor: setup — entity count and attribute alignment
# ---------------------------------------------------------------------------

class TestSensorSetup:
    def test_sensor_count(self):
        """Seven sensor types: removed standalone quantity, added max_sell and initial_fill_date."""
        from custom_components.trading212.sensor import SENSORS
        assert len(SENSORS) == 7

    def test_sensor_keys_match_position_attributes(self):
        """Every sensor key must resolve on a real Position object."""
        from custom_components.trading212.sensor import SENSORS
        pos = make_position(make_mock_api(), RAW_POSITION_1)
        for desc in SENSORS:
            assert getattr(pos, desc.key, None) is not None, (
                f"Sensor key '{desc.key}' not found on Position"
            )

    def test_all_sensor_keys_are_unique(self):
        from custom_components.trading212.sensor import SENSORS
        keys = [s.key for s in SENSORS]
        assert len(keys) == len(set(keys))

    def test_quantity_not_a_standalone_sensor(self):
        from custom_components.trading212.sensor import SENSORS
        assert not any(s.key == "quantity" for s in SENSORS)

    def test_quantity_available_for_trading_sensor_exists(self):
        from custom_components.trading212.sensor import SENSORS
        assert any(s.key == "max_sell" for s in SENSORS)

    def test_initial_fill_date_sensor_exists(self):
        from custom_components.trading212.sensor import SENSORS
        assert any(s.key == "initial_fill_date" for s in SENSORS)


# ---------------------------------------------------------------------------
# Sensor: extra_state_attributes
# ---------------------------------------------------------------------------

class TestSensorAttributes:
    def _make_sensor(self, key: str, raw_data_override: dict | None = None):
        from custom_components.trading212.sensor import Trading212Sensor, SENSORS
        raw = RAW_POSITION_1
        coord = make_coordinator([raw])
        coord.data = {raw["ticker"]: {**raw, **(raw_data_override or {})}}
        coord._listeners = {}
        coord.last_update_success = True

        description = next(s for s in SENSORS if s.key == key)

        with patch(
            "custom_components.trading212.entity.CoordinatorEntity.__init__",
            return_value=None,
        ):
            sensor = Trading212Sensor.__new__(Trading212Sensor)
            sensor.coordinator = coord
            sensor._ticker = raw["ticker"]
            sensor.position = coord.positions[raw["ticker"]]
            sensor.entity_description = description
            sensor._attr_unique_id = f"{raw['ticker']}-{key}"
            sensor._currency = "USD"

        return sensor

    def test_wallet_value_has_quantity_attribute(self):
        sensor = self._make_sensor("current_value")
        assert sensor.extra_state_attributes["quantity"] == pytest.approx(10.0)

    def test_wallet_value_has_quantity_in_pies_attribute(self):
        sensor = self._make_sensor("current_value")
        assert "quantity_in_pies" in sensor.extra_state_attributes

    def test_wallet_value_has_instrument_currency(self):
        sensor = self._make_sensor("current_value")
        assert sensor.extra_state_attributes["instrument_currency"] == "USD"

    def test_wallet_value_includes_wallet_impact_when_present(self):
        sensor = self._make_sensor("current_value", raw_data_override={
            "walletImpact": {
                "currency": "USD",
                "fxImpact": 1.5,
                "totalCost": 1500.0,
                "unrealizedProfitLoss": 250.0,
            }
        })
        attrs = sensor.extra_state_attributes
        assert attrs["wallet_impact_currency"] == "USD"
        assert attrs["wallet_impact_fx_impact"] == pytest.approx(1.5)
        assert attrs["wallet_impact_total_cost"] == pytest.approx(1500.0)
        assert attrs["wallet_impact_unrealized_profit_loss"] == pytest.approx(250.0)

    def test_wallet_value_omits_wallet_impact_when_absent(self):
        sensor = self._make_sensor("current_value")
        attrs = sensor.extra_state_attributes
        assert "wallet_impact_currency" not in attrs
        assert "wallet_impact_fx_impact" not in attrs

    def test_monetary_sensors_have_instrument_currency(self):
        for key in ("average_price", "current_price", "buy_value"):
            sensor = self._make_sensor(key)
            assert sensor.extra_state_attributes.get("instrument_currency") == "USD", (
                f"Expected instrument_currency on {key}"
            )

    def test_non_monetary_sensors_have_no_instrument_currency(self):
        for key in ("percent_change", "max_sell"):
            sensor = self._make_sensor(key)
            assert "instrument_currency" not in sensor.extra_state_attributes, (
                f"Did not expect instrument_currency on {key}"
            )

    def test_non_wallet_sensor_has_no_quantity_attribute(self):
        sensor = self._make_sensor("current_price")
        assert "quantity" not in sensor.extra_state_attributes


# ---------------------------------------------------------------------------
# Account Wallet sensors
# ---------------------------------------------------------------------------

RAW_ACCOUNT_SUMMARY: dict[str, Any] = {
    "id": 12345678,
    "currency": "GBP",
    "cash": {
        "availableToTrade": 500.00,
        "inPies": 100.00,
        "reservedForOrders": 50.00,
    },
    "investments": {
        "currentValue": 10000.00,
        "realizedProfitLoss": 250.00,
        "totalCost": 9500.00,
        "unrealizedProfitLoss": 500.00,
    },
    "totalValue": 10500.00,
}


class TestAccountWalletSensor:
    def _make_sensor(self, key: str, account_data: dict | None = None):
        from custom_components.trading212.account_sensor import (
            AccountWalletSensor,
            ACCOUNT_WALLET_SENSORS,
        )
        coord = make_coordinator()
        coord.account_data = account_data if account_data is not None else RAW_ACCOUNT_SUMMARY
        coord._listeners = {}
        coord.last_update_success = True

        description = next(s for s in ACCOUNT_WALLET_SENSORS if s.key == key)

        with patch(
            "custom_components.trading212.account_sensor.CoordinatorEntity.__init__",
            return_value=None,
        ):
            sensor = AccountWalletSensor.__new__(AccountWalletSensor)
            sensor.coordinator = coord
            sensor._account_id = "12345678"
            sensor._currency = "GBP"
            sensor.entity_description = description
            sensor._attr_unique_id = f"12345678_wallet_{key}"
            from homeassistant.helpers.device_registry import DeviceInfo
            sensor._attr_device_info = DeviceInfo(
                identifiers={("trading212", "12345678_wallet")},
                name="Account Wallet",
            )

        return sensor

    def test_sensor_count(self):
        from custom_components.trading212.account_sensor import ACCOUNT_WALLET_SENSORS
        assert len(ACCOUNT_WALLET_SENSORS) == 8

    def test_all_keys_unique(self):
        from custom_components.trading212.account_sensor import ACCOUNT_WALLET_SENSORS
        keys = [s.key for s in ACCOUNT_WALLET_SENSORS]
        assert len(keys) == len(set(keys))

    def test_available_to_trade(self):
        assert self._make_sensor("available_to_trade").native_value == pytest.approx(500.00)

    def test_cash_in_pies(self):
        assert self._make_sensor("cash_in_pies").native_value == pytest.approx(100.00)

    def test_reserved_for_orders(self):
        assert self._make_sensor("reserved_for_orders").native_value == pytest.approx(50.00)

    def test_investments_current_value(self):
        assert self._make_sensor("investments_current_value").native_value == pytest.approx(10000.00)

    def test_realized_profit_loss(self):
        assert self._make_sensor("realized_profit_loss").native_value == pytest.approx(250.00)

    def test_total_cost(self):
        assert self._make_sensor("total_cost").native_value == pytest.approx(9500.00)

    def test_unrealized_profit_loss(self):
        assert self._make_sensor("unrealized_profit_loss").native_value == pytest.approx(500.00)

    def test_total_value(self):
        assert self._make_sensor("total_value").native_value == pytest.approx(10500.00)

    def test_native_unit_is_account_currency(self):
        assert self._make_sensor("total_value").native_unit_of_measurement == "GBP"

    def test_currency_attribute(self):
        assert self._make_sensor("available_to_trade").extra_state_attributes["currency"] == "GBP"

    def test_returns_none_for_missing_path(self):
        sensor = self._make_sensor("available_to_trade", account_data={})
        assert sensor.native_value is None

    def test_returns_none_for_missing_nested_key(self):
        sensor = self._make_sensor("cash_in_pies", account_data={"cash": {}})
        assert sensor.native_value is None

    def test_unique_id_format(self):
        sensor = self._make_sensor("total_value")
        assert sensor._attr_unique_id == "12345678_wallet_total_value"

    def test_device_info_identifier(self):
        sensor = self._make_sensor("total_value")
        assert ("trading212", "12345678_wallet") in sensor._attr_device_info["identifiers"]

    def test_device_name_is_account_wallet(self):
        sensor = self._make_sensor("total_value")
        assert sensor._attr_device_info["name"] == "Account Wallet"
