"""Trading212 integration coordinator class."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from pytrading212api.api import Trading212API
from pytrading212api.exceptions import (
    Trading212AttemptsExceeded,
    Trading212BadApiKey,
    Trading212Error,
    Trading212Limited,
    Trading212TimeOut,
)
from pytrading212api.position import Position

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Minimum sensible poll floor — T212 limit is ~50 req/min on most endpoints.
# One bulk call per cycle means this is safe at any portfolio size.
_MIN_INTERVAL = timedelta(seconds=10)
# How long to back off when the library exhausts its internal retries.
_RATE_LIMIT_BACKOFF = timedelta(seconds=60)


class Trading212Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Single coordinator for the whole account.

    Fetches all positions in one bulk API call per poll cycle and exposes
    them as coordinator.data keyed by ticker.  Per-position entities read
    from that dict rather than triggering individual API calls.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: Trading212API,
        positions: list[Position],
        instrument_names: dict[str, tuple[str, str, str, str, str]],
        interval: int,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=max(timedelta(seconds=interval), _MIN_INTERVAL),
        )
        self.api = api
        # Keyed by ticker for O(1) lookup in entities.
        self.positions: dict[str, Position] = {p.ticker: p for p in positions}
        # Maps ticker → (full_name, short_name) e.g. ("Nvidia Corp", "NVDA").
        self.instrument_names = instrument_names
        self.config_entry: ConfigEntry = entry
        self._base_interval = max(timedelta(seconds=interval), _MIN_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all positions in a single bulk API call."""
        try:
            raw_positions: list[dict] = await self.api.get_positions()
        except Trading212BadApiKey as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for {self.config_entry.data[CONF_ID]}"
            ) from err
        except Trading212AttemptsExceeded as err:
            # The library already retried and kept hitting the limit.
            # Back off for a full reset window before the next coordinator tick.
            _LOGGER.warning(
                "Rate limit retries exhausted, backing off for %s seconds",
                _RATE_LIMIT_BACKOFF.seconds,
            )
            self.update_interval = _RATE_LIMIT_BACKOFF
            raise UpdateFailed(err) from err
        except (Trading212Limited, Trading212TimeOut, Trading212Error) as err:
            raise UpdateFailed(err) from err
        else:
            # Restore the configured interval after a successful fetch in case
            # it was temporarily extended by a previous rate-limit backoff.
            if self.update_interval != self._base_interval:
                _LOGGER.debug("Restoring base poll interval after backoff")
                self.update_interval = self._base_interval

        # Update Position objects in-place so entity state reflects new data,
        # and build the data dict the coordinator exposes to entities.
        data: dict[str, Any] = {}
        for raw in raw_positions:
            ticker = raw["ticker"]
            if ticker in self.positions:
                # _update_position is the library's own method — we're calling
                # it with fresh bulk data instead of letting each position make
                # its own API call.
                self.positions[ticker]._update_position(raw)  # noqa: SLF001
            else:
                # New position opened since integration setup — create it.
                _LOGGER.debug("New position detected: %s", ticker)
                self.positions[ticker] = Position(self.api, raw)
            data[ticker] = raw

        return data
