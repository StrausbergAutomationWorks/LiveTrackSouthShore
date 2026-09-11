"""Sensor entities for the South Shore Line tracker.

One summary sensor. Positions live on the geo_location platform, one entity
per vehicle.

! The 28 slot sensors were retired 2026-09-11. A fixed pool of entities with
trains assigned into it was how a varying number of markers used to be shown;
geo_location creates an entity per vehicle as it appears, so the pool had
nothing left to do. See 05_SHARED_LESSONS.md D6.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN
from .coordinator import SouthShoreCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the summary sensor."""
    # Built in __init__.py and shared with the geo_location platform, so both
    # run off one poll of the feed.
    coordinator: SouthShoreCoordinator = hass.data[DOMAIN][entry.entry_id]

    device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="South Shore Line",
        manufacturer="NICTD",
        model="GTFS-Realtime via ETA SPOT",
        configuration_url="https://mysouthshoreline.com",
    )
    async_add_entities([SouthShoreCountSensor(coordinator, entry, device)])


class SouthShoreCountSensor(SensorEntity):
    """How many trains are currently running."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "trains"

    def __init__(
        self,
        coordinator: SouthShoreCoordinator,
        entry: ConfigEntry,
        device: DeviceInfo,
    ) -> None:
        self._coordinator = coordinator
        self._attr_device_info = device
        self._attr_name = "Trains Running"
        self._attr_unique_id = f"{entry.entry_id}_count"

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> int:
        return (self._coordinator.data or {}).get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._coordinator.data or {}
        vehicles = data.get("vehicles") or {}
        delayed = sorted({
            r["train"] for r in vehicles.values()
            if r.get("in_service") and r.get("delay_min") is not None
            and r["delay_min"] >= 5
        })
        return {
            # Trains, not vehicles: every unit of a consist transmits its own
            # position, so the vehicle count runs several times the train
            # count. Both are published because both are asked for.
            "trains_running": data.get("running", []),
            "vehicles_total": len(vehicles),
            # Non-revenue equipment, which NICTD labels NIS. A deadheading
            # consist is a real movement on real track, so it gets a marker
            # like anything else - this is the count, not a filter.
            "not_in_service": data.get("not_in_service", 0),
            "delayed_5min_plus": delayed,
            "worst_delay_min": max(
                (r["delay_min"] for r in vehicles.values()
                 if r.get("delay_min") is not None),
                default=None,
            ),
            "feed_timestamp": data.get("feed_timestamp"),
            "last_update": data.get("last_update"),
        }
