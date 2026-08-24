"""Sensor entities for the South Shore Line tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN, LIVE_TRAIN_SLOTS
from .coordinator import SouthShoreCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the slot entities plus one summary sensor."""
    coordinator = SouthShoreCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="South Shore Line",
        manufacturer="NICTD",
        model="GTFS-Realtime via ETA SPOT",
        configuration_url="https://mysouthshoreline.com",
    )

    entities: list[SensorEntity] = [
        SouthShoreTrainSensor(coordinator, entry, slot, device)
        for slot in range(1, LIVE_TRAIN_SLOTS + 1)
    ]
    entities.append(SouthShoreCountSensor(coordinator, entry, device))
    async_add_entities(entities)


class _Base(SensorEntity):
    """Shared wiring."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False

    def __init__(self, coordinator: SouthShoreCoordinator, device: DeviceInfo) -> None:
        self._coordinator = coordinator
        self._attr_device_info = device

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )


class SouthShoreTrainSensor(_Base):
    """One slot in the live-position pool.

    State is the train number while occupied, otherwise 'idle'. Latitude and
    longitude are published only when occupied, so Home Assistant's map plots
    the train while it runs and shows nothing - rather than a stale marker -
    once it has finished.
    """

    _attr_icon = "mdi:train"

    def __init__(self, coordinator, entry: ConfigEntry, slot: int, device) -> None:
        super().__init__(coordinator, device)
        self._slot = slot
        self._attr_name = f"South Shore Train {slot}"
        self._attr_unique_id = f"{entry.entry_id}_train_{slot}"

    def _train(self) -> dict[str, Any] | None:
        slots = (self._coordinator.data or {}).get("slots") or []
        if self._slot - 1 < len(slots):
            return slots[self._slot - 1]
        return None

    @property
    def native_value(self) -> str:
        train = self._train()
        return train["train"] if train else "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        train = self._train()
        if not train:
            return {"slot": self._slot, "occupied": False}

        attrs: dict[str, Any] = {
            "slot": self._slot,
            "occupied": True,
            "train": train.get("train"),
            "vehicle_id": train.get("vehicle_id"),
            "delay_min": train.get("delay_min"),
            "on_time": train.get("on_time"),
            # Derived from successive positions: the feed reports bearing 0
            # for every vehicle, so it cannot be read directly.
            "bearing": train.get("bearing"),
            "feed_timestamp": (self._coordinator.data or {}).get("feed_timestamp"),
        }
        # Home Assistant's map keys on these exact attribute names.
        if train.get("latitude") is not None and train.get("longitude") is not None:
            attrs["latitude"] = train["latitude"]
            attrs["longitude"] = train["longitude"]
        return attrs


class SouthShoreCountSensor(_Base):
    """How many trains are currently running."""

    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "trains"

    def __init__(self, coordinator, entry: ConfigEntry, device) -> None:
        super().__init__(coordinator, device)
        self._attr_name = "South Shore Trains Running"
        self._attr_unique_id = f"{entry.entry_id}_count"

    @property
    def native_value(self) -> int:
        return (self._coordinator.data or {}).get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._coordinator.data or {}
        trains = data.get("trains") or {}
        delayed = [
            t["train"] for t in trains.values()
            if t.get("delay_min") is not None and t["delay_min"] >= 5
        ]
        return {
            "slots_total": LIVE_TRAIN_SLOTS,
            "slots_free": LIVE_TRAIN_SLOTS - data.get("count", 0),
            "trains_running": sorted(trains),
            "delayed_5min_plus": sorted(delayed),
            "worst_delay_min": max(
                (t["delay_min"] for t in trains.values()
                 if t.get("delay_min") is not None),
                default=None,
            ),
            "last_update": data.get("last_update"),
        }
