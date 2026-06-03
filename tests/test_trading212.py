"""Tests for the Trading212 custom integration.

Strategy: unit-test the coordinator and entity logic directly, mocking
the HA DataUpdateCoordinator infrastructure and the pytrading212api
library.  This avoids the full HA test harness (pytest-homeassistant-
custom-component) while still exercising all meaningful code paths.

Run with:
    pytest tests/ -v --tb=short
"""

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

# Same as RAW_POSITION_1 but with updated price and P&L
RAW_POSITION_UPDATED: dict[str, Any] = {
    **RAW_POSITION_1,
    "currentPrice": 180.00,
    "ppl": 300.00,
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
    """Minimal mock of HomeAssistant needed by DataUpdateCoordinator."""
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


def make_coordinator(raw_positions=None, interval=30, api_exception=None):
    """Build a Trading212Coordinator with DataUpdateCoordinator.__init__ patched out."""
    from custom_components.trading212.coordinator import Trading212Coordinator

    if raw_positions is None:
        raw_positions = [RAW_POSITION_1]

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
        coord = Trading212Coordinator(hass, api, positions, interval, entry)

    # Populate attributes that super().__init__ would normally set
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
            coord = Trading212Coordinator(make_mock_hass(), api, positions, 30, make_mock_config_entry())

        assert "AAPL_US_EQ" in coord.positions
        assert "MSFT_US_EQ" in coord.positions
        assert coord.positions["AAPL_US_EQ"].ticker == "AAPL_US_EQ"

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
            Trading212Coordinator(make_mock_hass(), api, positions, 1, make_mock_config_entry())

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
            Trading212Coordinator(make_mock_hass(), api, positions, 60, make_mock_config_entry())

        assert captured["update_interval"] == timedelta(seconds=60)

    def test_api_stored_on_coordinator(self):
        from custom_components.trading212.coordinator import Trading212Coordinator

        api = make_mock_api()
        positions = [make_position(api, RAW_POSITION_1)]

        with patch(
            "custom_components.trading212.coordinator.DataUpdateCoordinator.__init__",
            return_value=None,
        ):
            coord = Trading212Coordinator(make_mock_hass(), api, positions, 30, make_mock_config_entry())

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
        """The same Position object must be mutated, not replaced."""
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
        assert coord.positions["MSFT_US_EQ"].ticker == "MSFT_US_EQ"

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
        """Backoff must not be reset by the failed update itself."""
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
        p = self._make(RAW_POSITION_1)
        assert p.ticker == "AAPL_US_EQ"

    def test_quantity(self):
        p = self._make(RAW_POSITION_1)
        assert p.quantity == pytest.approx(10.0)

    def test_average_price(self):
        p = self._make(RAW_POSITION_1)
        assert p.average_price == pytest.approx(150.00)

    def test_current_price(self):
        p = self._make(RAW_POSITION_1)
        assert p.current_price == pytest.approx(175.00)

    def test_computed_buy_value(self):
        p = self._make(RAW_POSITION_1)
        assert p.buy_value == pytest.approx(150.00 * 10.0)

    def test_computed_current_value(self):
        p = self._make(RAW_POSITION_1)
        assert p.current_value == pytest.approx(175.00 * 10.0)

    def test_percent_change_positive(self):
        p = self._make(RAW_POSITION_1)
        # ppl=250, buy_value=1500 → (250/1500)*100 = 16.67
        assert p.percent_change == pytest.approx(round(250.0 / 1500.0 * 100, 2))

    def test_percent_change_zero_buy_value_does_not_raise(self):
        raw = {**RAW_POSITION_1, "quantity": 0.0, "averagePrice": 0.0}
        p = self._make(raw)
        assert p.percent_change == 0.0

    def test_update_position_mutates_current_price(self):
        p = self._make(RAW_POSITION_1)
        assert p.current_price == 175.00
        p._update_position(RAW_POSITION_UPDATED)
        assert p.current_price == 180.00

    def test_update_position_recalculates_current_value(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        assert p.current_value == pytest.approx(180.00 * 10.0)

    def test_update_position_buy_value_unchanged_when_price_and_qty_same(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        # averagePrice and quantity unchanged in RAW_POSITION_UPDATED
        assert p.buy_value == pytest.approx(150.00 * 10.0)

    def test_update_position_recalculates_percent_change(self):
        p = self._make(RAW_POSITION_1)
        p._update_position(RAW_POSITION_UPDATED)
        # ppl=300, buy_value=1500 → 20.0%
        assert p.percent_change == pytest.approx(round(300.0 / 1500.0 * 100, 2))


# ---------------------------------------------------------------------------
# Entity base class
# ---------------------------------------------------------------------------

class TestBaseEntity:
    def _make_entity(self, raw=None):
        from custom_components.trading212.entity import Trading212BaseEntity
        if raw is None:
            raw = RAW_POSITION_1
        coord = make_coordinator([raw])
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

        return entity, coord

    def test_device_info_identifier_contains_ticker(self):
        entity, _ = self._make_entity()
        info = entity.device_info
        assert ("trading212", "AAPL_US_EQ") in info["identifiers"]

    def test_device_info_name_contains_ticker(self):
        entity, _ = self._make_entity()
        assert "AAPL_US_EQ" in entity.device_info["name"]

    def test_position_attribute_is_same_object_as_coordinator(self):
        entity, coord = self._make_entity()
        assert entity.position is coord.positions["AAPL_US_EQ"]

    def test_position_reflects_coordinator_update(self):
        """entity.position is a live reference — mutations on coord.positions show through."""
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

    def test_quantity(self):
        assert self._make_sensor("quantity").native_value == pytest.approx(10.0)

    def test_current_value(self):
        assert self._make_sensor("current_value").native_value == pytest.approx(1750.00)

    def test_buy_value(self):
        assert self._make_sensor("buy_value").native_value == pytest.approx(1500.00)

    def test_percent_change(self):
        assert self._make_sensor("percent_change").native_value == pytest.approx(
            round(250.0 / 1500.0 * 100, 2)
        )

    def test_unique_id_format(self):
        sensor = self._make_sensor("current_price")
        assert sensor._attr_unique_id == "AAPL_US_EQ-current_price"

    def test_native_value_reflects_position_update(self):
        """native_value reads live from self.position — mutations are immediately visible."""
        sensor = self._make_sensor("current_price")
        assert sensor.native_value == pytest.approx(175.00)
        sensor.position._update_position(RAW_POSITION_UPDATED)
        assert sensor.native_value == pytest.approx(180.00)


# ---------------------------------------------------------------------------
# Sensor: setup — entity count and attribute alignment
# ---------------------------------------------------------------------------

class TestSensorSetup:
    def test_sensor_count(self):
        """Exactly six sensor types are defined."""
        from custom_components.trading212.sensor import SENSORS
        assert len(SENSORS) == 6

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
