"""geo_location entities for the South Shore Line tracker.

One entity per VEHICLE, not per slot. Every unit of a multiple-unit consist
transmits its own position, so a three-car train is three markers; the
`in_service` attribute and the marker label distinguish the controlling unit
from its trailing NIS units.

Contract: 10_SEED/05_SHARED_LESSONS.md section D.

  * `state` is @final and IS the distance. Do not add a distance attribute.
  * `state_attributes` is @final and returns only source/latitude/longitude.
    Everything else goes in extra_state_attributes or it is silently dropped.
  * `_attr_source` is mandatory - it is what the shared map filters on.
  * The registry row is KEPT. A railcar recurs, so removing the row and
    re-registering the same unique_id makes Home Assistant append a number
    and entity ids drift upward forever (D6a-0b).
  * `_attr_name` is built from vehicle.id, never from the label. Ten of
    twelve vehicles are labelled "NIS"; naming from that would collide and
    produce nis, nis_2, nis_3 ... (D6b).

! MOTION. This integration must NOT emit max_extrapolation_s: the feed sets
no speed at all and its bearing is present on every vehicle and always
exactly 0.0, which fails condition 1 of the eligibility test (D3b-ii). That
is not permission to sit still - the previous_* fields let the map
interpolate between two MEASURED fixes, which is the other mechanism
entirely.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.location import distance as _distance

from .const import ATTRIBUTION, DOMAIN
from .coordinator import SouthShoreCoordinator

# Stacking order on the shared map. Ships use 20; trains sit above them so a
# marker on land is not hidden under one on the lake.
Z_INDEX_OFFSET = 25


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one entity per vehicle, adding more as new units appear."""
    coordinator: SouthShoreCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync() -> None:
        vehicles = (coordinator.data or {}).get("vehicles") or {}
        new = [v for v in vehicles if v not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            SouthShoreVehicle(coordinator, entry, veh_id) for veh_id in new
        )

    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))


class SouthShoreVehicle(GeolocationEvent):
    """One South Shore vehicle on the shared map."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_icon = "mdi:train"
    _attr_unit_of_measurement = "km"
    # The discriminator the shared map's auto-entities card filters on.
    _attr_source = DOMAIN

    def __init__(
        self,
        coordinator: SouthShoreCoordinator,
        entry: ConfigEntry,
        vehicle_id: str,
    ) -> None:
        self._coordinator = coordinator
        self._vehicle_id = vehicle_id
        self._attr_unique_id = f"{entry.entry_id}_vehicle_{vehicle_id}"
        # ! From the stable unit number, never from the label. See D6b.
        self._attr_name = f"South Shore unit {vehicle_id}"

    def _rec(self) -> dict[str, Any] | None:
        return ((self._coordinator.data or {}).get("vehicles") or {}).get(
            self._vehicle_id
        )

    @property
    def available(self) -> bool:
        # A vehicle absent from the feed is not "departed" - it has simply
        # stopped being heard. The entity stays registered and goes
        # unavailable; last_seen carries the real age.
        return self._coordinator.last_update_success and self._rec() is not None

    @property
    def latitude(self) -> float | None:
        rec = self._rec()
        return rec["latitude"] if rec else None

    @property
    def longitude(self) -> float | None:
        rec = self._rec()
        return rec["longitude"] if rec else None

    @property
    def distance(self) -> float | None:
        """Kilometres from the instance's configured home location.

        state is @final and returns round(self.distance, 1), so this IS the
        state. Nothing else should publish a distance.
        """
        rec = self._rec()
        if not rec:
            return None
        metres = _distance(
            self.hass.config.latitude,
            self.hass.config.longitude,
            rec["latitude"],
            rec["longitude"],
        )
        return None if metres is None else metres / 1000

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rec = self._rec()
        if not rec:
            return {}

        attrs: dict[str, Any] = {
            "identity": rec["vehicle_id"],
            "marker_label": rec["marker_label"],
            "vehicle_id": rec["vehicle_id"],
            "train": rec["train"],
            "in_service": rec["in_service"],
            "last_seen": rec["observed_at"],
            "z_index_offset": Z_INDEX_OFFSET,
        }
        # Absent values are OMITTED, never sentinels: a wrong value is worse
        # than a missing one because the consumer cannot tell.
        #
        # heading_deg is never present. The feed's bearing is 0.0 on every
        # vehicle, so which way a unit FACES is unknown and nothing should
        # rotate a marker by it.
        for key in (
            "course_deg",
            "previous_latitude",
            "previous_longitude",
            "previous_observed_at",
            "segment_duration_s",
        ):
            if key in rec:
                attrs[key] = rec[key]
        if rec.get("delay_min") is not None:
            attrs["delay_min"] = rec["delay_min"]
        return attrs

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )
