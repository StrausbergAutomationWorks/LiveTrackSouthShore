"""Vehicle record -> geo_location attributes. The ONE place that mapping lives.

No Home Assistant imports, so it can be tested alone.

Instants are published as ISO 8601 UTC with an explicit offset
(06_MAP_CONTRACT.md D0), e.g. 2026-09-20T04:58:32+00:00. The coordinator keeps
them as integer epoch seconds because its fix arithmetic subtracts them; they
are converted here and nowhere else. Durations stay numeric: `segment_duration_s`
is seconds and equals observed_at - previous_observed_at.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# The shared map's layer (06_MAP_CONTRACT.md D10). Every unit is a train,
# NIS units included (D8), so one name for all of them. The card maps the name
# to its stacking offset; the numeric z_index_offset attribute this replaced
# was retired by D10 - the card never read it.
#
# No object_ids (D11): the feed states no MMSI, IMO, ICAO address or
# registration, and a vehicle or trip id is not one of them.
MAP_LAYER = "rail"

# Carried over from the record unchanged when present.
#
# line and the colour keys: set by the coordinator from lines.styling(), only
# when the trip id is a train number (D4a rule 3: no colour -> no key). The
# outline keys are per line - each line carries only the ones it sets, and
# the card draws its default dark outline where one is absent (D4a rule 6b).
# The card (0.1.0+2227ef0) reads all of them.
#
# icon_rotation_deg / icon_rotation_basis: the arrow's direction, "course" or
# "held" (motion.rotation). A DISPLAY field; course_deg stays the measurement.
_PASSTHROUGH = ("course_deg", "previous_latitude", "previous_longitude",
                "segment_duration_s", "line", "marker_color",
                "marker_label_color", "marker_label_outline_color",
                "marker_arrow_outline_color",
                "icon_rotation_deg", "icon_rotation_basis")


def iso_utc(epoch_s: int) -> str:
    """Epoch seconds -> '2026-09-20T04:58:32+00:00'."""
    return datetime.fromtimestamp(int(epoch_s), tz=timezone.utc).isoformat()


def to_attributes(rec: dict[str, Any]) -> dict[str, Any]:
    """Map one vehicle record to its extra_state_attributes."""
    attrs: dict[str, Any] = {
        "identity": rec["vehicle_id"],
        "marker_label": rec["marker_label"],
        "vehicle_id": rec["vehicle_id"],
        "train": rec["train"],
        "in_service": rec["in_service"],
        "map_layer": MAP_LAYER,
    }
    # observed_at: when the PUBLISHED position was true (D2). last_seen is the
    # same instant - the vehicle's own timestamp is the last we heard of it.
    # Both are OMITTED when the vehicle carried no timestamp: the feed header
    # time is when the feed was built, not when the unit was observed, and
    # publishing it is the Brightline mistake (backlog 121) again.
    if rec.get("observed_at") is not None:
        attrs["observed_at"] = iso_utc(rec["observed_at"])
        attrs["last_seen"] = attrs["observed_at"]
    # Absent values are OMITTED, never sentinels: a wrong value is worse than
    # a missing one because the consumer cannot tell.
    #
    # heading_deg is never present. The feed's bearing is 0.0 on every
    # vehicle, so which way a unit FACES is unknown and nothing should rotate
    # a marker by it.
    for key in _PASSTHROUGH:
        if key in rec:
            attrs[key] = rec[key]
    if rec.get("previous_observed_at") is not None:
        attrs["previous_observed_at"] = iso_utc(rec["previous_observed_at"])
    if rec.get("delay_min") is not None:
        attrs["delay_min"] = rec["delay_min"]
    return attrs
