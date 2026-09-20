"""Per-vehicle fix tracking. No Home Assistant imports, so it can be tested alone.

Times here are INTEGER epoch seconds throughout; the fix arithmetic subtracts
them. Conversion to ISO 8601 happens once, at publication (attributes.py).
"""

from __future__ import annotations

import math
from typing import Any

# A fix is (lat, lon, t, t_is_observation).
#
# t_is_observation is False when the vehicle carried no GTFS-RT timestamp and
# t is the FeedHeader timestamp instead. That is when the FEED was generated,
# not when the vehicle was observed (06_MAP_CONTRACT.md D2), so it is kept only
# to tell a duplicate poll from a new one and is never published.
Fix = tuple[float, float, int, bool]

# Longest gap still treated as one segment. Longer means the unit dropped out
# of the feed and came back; interpolating across that would be invention.
MAX_SEGMENT_S = 600


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float | None:
    """Bearing from a to b, or None if they are effectively the same point."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    # ~10 m; below this the train is stopped and any bearing is noise
    if abs(b[0] - a[0]) < 1e-4 and abs(b[1] - a[1]) < 1e-4:
        return None
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def track(
    fixes: dict[str, Fix],
    prev_fixes: dict[str, Fix],
    veh_id: str,
    here: tuple[float, float],
    t: int,
    t_is_observation: bool,
) -> dict[str, Any]:
    """Record one poll of one vehicle and return its motion fields.

    Returns a dict holding only what is known: `observed_at` (int) when the
    newest fix carries a real observation time; `course_deg` when the unit
    moved between its last two distinct fixes; the `previous_*` fields and
    `segment_duration_s` when BOTH fixes carry real observation times and the
    gap is plausible. Anything unknown is omitted, never a sentinel (D0).

    ! D3c-iii. Advance only on a genuinely NEW observation. Poll and feed are
    both 30 s, so they alias and roughly one poll in three returns a fix
    identical to the last. A duplicate must not become the "previous" fix, or
    the segment collapses to zero length and the fields drop out on alternate
    updates - a stutter on the map.
    """
    cur = fixes.get(veh_id)
    if cur is None or cur[2] != t or (cur[0], cur[1]) != here:
        if cur is not None:
            prev_fixes[veh_id] = cur
        fixes[veh_id] = (here[0], here[1], t, t_is_observation)

    latest = fixes[veh_id]
    prev = prev_fixes.get(veh_id)
    out: dict[str, Any] = {}

    if latest[3]:
        out["observed_at"] = latest[2]

    if prev is not None:
        course = bearing((prev[0], prev[1]), (latest[0], latest[1]))
        if course is not None:
            out["course_deg"] = round(course, 1)
        # The segment is built on the two observation times. If either is a
        # feed time there is no measured interval, so no segment at all -
        # D2: segment_duration_s = observed_at - previous_observed_at, and
        # with no observed_at there is nothing for it to equal.
        if latest[3] and prev[3]:
            seg = latest[2] - prev[2]
            if 0 < seg <= MAX_SEGMENT_S:
                out["previous_latitude"] = prev[0]
                out["previous_longitude"] = prev[1]
                out["previous_observed_at"] = prev[2]
                out["segment_duration_s"] = seg
    return out


def rotation(held: dict[str, float], veh_id: str,
             course_deg: float | None) -> dict[str, float | str]:
    """Which way the marker's arrow points, holding it while the unit stands.

    Uses Live Track Aircraft's vocabulary (06_MAP_CONTRACT.md D4):
    `icon_rotation_deg` plus `icon_rotation_basis`, here "course" when the
    unit moved between its last two distinct fixes and "held" when it did not
    and an earlier good bearing exists. Decided by Lee 2026-09-20: a stopped
    train keeps the last good bearing.

    ! course_deg itself still disappears at rest - D3c-iii says that omission
    is correct and must not be "fixed". The held value is a DISPLAY field and
    lives under its own key, so no consumer mistakes it for a measurement.
    A unit first seen standing still has no bearing at all: omitted (D0).
    """
    if course_deg is not None:
        held[veh_id] = course_deg
        return {"icon_rotation_deg": course_deg, "icon_rotation_basis": "course"}
    if veh_id in held:
        return {"icon_rotation_deg": held[veh_id], "icon_rotation_basis": "held"}
    return {}


def forget_absent(fixes: dict[str, Fix], prev_fixes: dict[str, Fix], present,
                  held: dict[str, float] | None = None) -> None:
    """Drop remembered fixes (and held bearings) for vehicles no longer in the feed."""
    for gone in [k for k in fixes if k not in present]:
        del fixes[gone]
        prev_fixes.pop(gone, None)
    if held is not None:
        for gone in [k for k in held if k not in present]:
            del held[gone]
