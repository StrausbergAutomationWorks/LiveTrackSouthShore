"""Coordinator: fetch NICTD positions + delays, one record per vehicle."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from google.transit import gtfs_realtime_pb2

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_TRANSIENT_FAILURES,
    POSITIONS_URL,
    REQUEST_TIMEOUT,
    TRIP_UPDATES_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class SouthShoreCoordinator(DataUpdateCoordinator):
    """Poll both realtime feeds and expose one record per vehicle."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        opts = {**entry.data, **entry.options}
        interval = int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

        super().__init__(
            hass,
            _LOGGER,
            name="South Shore Line",
            update_interval=timedelta(seconds=interval),
        )
        self._session = async_get_clientsession(hass)

        # Previous fix per VEHICLE, for the geo_location platform.
        #
        # ! Keyed by vehicle.id, NOT by trip_id. The slot path keys on
        # trip_id, which COLLIDES: two trailing NIS units can carry the same
        # trip_id and the second then overwrites the first. Measured
        # 2026-09-06 - 12 vehicles in the feed but only 11 distinct trip_ids
        # (vehicle 12 and vehicle 35 both reported trip 509), so one vehicle
        # was silently dropped. vehicle.id was set and unique on all twelve.
        #
        # TWO fixes are held per vehicle, both (lat, lon, observed_at):
        #   _fix       the most recent DISTINCT observation
        #   _prev_fix  the distinct observation before that
        #
        # ! They must be distinct, not merely consecutive. The coordinator
        # polls every 30 s and the feed republishes every 30 s, so the two
        # alias and roughly one poll in three returns a fix identical to the
        # last. Measured 2026-09-11 over ten samples: three returned an
        # unchanged observed_at. Storing those duplicates made course_deg and
        # the previous_* fields appear and vanish on alternate updates, which
        # the map renders as a stutter. Advancing only on a genuinely new
        # observation keeps the emitted segment stable between real fixes.
        self._fix: dict[str, tuple[float, float, int]] = {}
        self._prev_fix: dict[str, tuple[float, float, int]] = {}

        # A single failed fetch should not blank every marker. The S3 feed is
        # normally fast and reliable - 40 consecutive requests on 2026-08-25
        # returned 0 failures at a median 0.15 s - but 9 transient failures
        # were logged across one day, most likely brief network drops on the
        # host. Tolerate a couple before declaring the coordinator failed.
        self._consecutive_failures = 0
        self._last_good: dict[str, Any] | None = None

    async def _fetch_feed(self, url: str) -> gtfs_realtime_pb2.FeedMessage | None:
        """Fetch and decode one protobuf feed, or None on any failure."""
        headers = {"User-Agent": USER_AGENT}
        try:
            async with self._session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("%s returned HTTP %s", url, resp.status)
                    return None
                raw = await resp.read()
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Could not fetch %s", url, exc_info=True)
            return None

        try:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(raw)
            return feed
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not decode %s", url, exc_info=True)
            return None

    @staticmethod
    def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float | None:
        """Bearing from a to b, or None if they are effectively the same point."""
        import math

        lat1, lon1 = math.radians(a[0]), math.radians(a[1])
        lat2, lon2 = math.radians(b[0]), math.radians(b[1])
        dlon = lon2 - lon1
        # ~10 m; below this the train is stopped and any bearing is noise
        if abs(b[0] - a[0]) < 1e-4 and abs(b[1] - a[1]) < 1e-4:
            return None
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        return (math.degrees(math.atan2(y, x)) + 360) % 360

    async def _async_update_data(self) -> dict[str, Any]:
        pos_feed = await self._fetch_feed(POSITIONS_URL)
        if pos_feed is None:
            self._consecutive_failures += 1
            if (self._consecutive_failures <= MAX_TRANSIENT_FAILURES
                    and self._last_good is not None):
                # Serve the previous result rather than blanking the map.
                # feed_timestamp on every entity carries the real age, so a
                # stale position is visible as stale rather than presented as
                # current.
                _LOGGER.debug(
                    "Positions feed unavailable (%s consecutive); serving the "
                    "previous result", self._consecutive_failures)
                return self._last_good
            raise UpdateFailed(
                f"positions feed unavailable "
                f"({self._consecutive_failures} consecutive failures)")
        self._consecutive_failures = 0
        trip_feed = await self._fetch_feed(TRIP_UPDATES_URL)  # best-effort

        # --- delays, keyed by train number ---
        delays: dict[str, int] = {}
        if trip_feed is not None:
            for ent in trip_feed.entity:
                if not ent.HasField("trip_update"):
                    continue
                tu = ent.trip_update
                train = (tu.trip.trip_id or "").strip()
                if not train:
                    continue
                # Only delay and stop_sequence are published - no stop_id and
                # no absolute times, so the soonest upcoming stop is the best
                # available "how late is it right now".
                best = None
                for stu in tu.stop_time_update:
                    if stu.HasField("arrival") and stu.arrival.delay:
                        if best is None or stu.stop_sequence < best[0]:
                            best = (stu.stop_sequence, stu.arrival.delay)
                if best:
                    delays[train] = int(best[1])

        feed_ts = int(getattr(pos_feed.header, "timestamp", 0) or 0)

        # --- positions ---
        vehicles: dict[str, dict[str, Any]] = {}
        not_in_service = 0
        for ent in pos_feed.entity:
            if not ent.HasField("vehicle"):
                continue
            v = ent.vehicle
            # route_id is always empty in this feed - NICTD runs one line, so
            # everything present belongs to us. Do NOT filter on route.
            label = (v.vehicle.label or "").strip()
            train = (v.trip.trip_id or label).strip()
            if not train:
                continue

            # NICTD labels a vehicle "NIS" - Not In Service - when it is not
            # the controlling unit of a revenue train.
            #
            # This matters more than it first appears. South Shore runs
            # multiple-unit electric consists and EVERY UNIT TRANSMITS ITS OWN
            # POSITION. The lead unit carries the train number; the trailing
            # units report as NIS. Without this filter one train renders as two
            # or three markers travelling in convoy a few tens of metres apart.
            #
            # Measured 2026-08-24, three samples a minute apart:
            #   train 311 + NIS 1060      moved 762 m and 769 m  (2-unit consist)
            #   train 25 + NIS 32 + NIS 35 moved 830, 848, 925 m (3-unit consist)
            # Same speed, same heading, 20-100 m apart throughout.
            #
            # Genuinely non-revenue moves are also labelled NIS (trip 133 was
            # running alone at ~6 mph during the same window), so the label
            # covers both cases. Both are REAL MOVEMENTS on real track and
            # both get a marker; in_service is what distinguishes them.
            #
            # NIS vehicles additionally have no stop_id and an empty
            # stop_time_update list, but the label is the explicit marker.
            in_service = label.upper() != "NIS"
            if not in_service:
                not_in_service += 1
            lat = getattr(v.position, "latitude", None)
            lon = getattr(v.position, "longitude", None)
            if not lat or not lon:
                continue

            here = (round(float(lat), 6), round(float(lon), 6))

            # --- per-VEHICLE record for the geo_location platform ---
            #
            # Identity is vehicle.id: set and unique on every vehicle,
            # including trailing NIS units. Fall back to the feed entity id,
            # which is itself "vehicle_position_<id>".
            veh_id = (v.vehicle.id or "").strip() or ent.id.strip()
            if veh_id:
                obs_at = int(v.timestamp) if v.HasField("timestamp") else feed_ts

                # Advance only on a genuinely NEW observation. A duplicate
                # poll must not become the "previous" fix, or the segment
                # collapses to zero length and the fields drop out.
                cur = self._fix.get(veh_id)
                if cur is None or cur[2] != obs_at or (cur[0], cur[1]) != here:
                    if cur is not None:
                        self._prev_fix[veh_id] = cur
                    self._fix[veh_id] = (here[0], here[1], obs_at)

                prev = self._prev_fix.get(veh_id)
                latest = self._fix[veh_id]
                course = None
                if prev is not None:
                    course = self._bearing((prev[0], prev[1]),
                                           (latest[0], latest[1]))

                rec: dict[str, Any] = {
                    "vehicle_id": veh_id,
                    "train": train,
                    "in_service": in_service,
                    "latitude": here[0],
                    "longitude": here[1],
                    "observed_at": latest[2],
                    # Option 1 labelling, decided 2026-09-11: the train number
                    # for a controlling unit, "NIS <unit>" for a trailing one.
                    # No inference. Consist-aware labels ("609 +2") need
                    # proximity association - backlog item 13 - and NOT
                    # trip_id, which does not identify the consist.
                    "marker_label": train if in_service else f"NIS {veh_id}",
                    "delay_min": (round(delays[train] / 60)
                                  if train in delays else None),
                }
                # Absent values are OMITTED, never sentinels. heading_deg is
                # never known here: the feed's bearing is always 0.0, so there
                # is nothing to rotate a marker by.
                if course is not None:
                    rec["course_deg"] = round(course, 1)
                if prev is not None:
                    seg = latest[2] - prev[2]
                    # previous_* let the map INTERPOLATE between two MEASURED
                    # fixes. This is the other motion mechanism entirely: the
                    # integration must never extrapolate (D3b-ii), but "no
                    # extrapolation" is NOT "no motion".
                    if 0 < seg <= 600:
                        rec["previous_latitude"] = prev[0]
                        rec["previous_longitude"] = prev[1]
                        rec["previous_observed_at"] = prev[2]
                        rec["segment_duration_s"] = seg
                vehicles[veh_id] = rec

        # Forget remembered fixes for vehicles no longer in the feed, so a
        # returning unit starts a fresh segment rather than interpolating
        # across a gap of hours. The ENTITY is kept either way - registry rows
        # are never removed for anything that recurs (D6a-0b).
        for gone in [k for k in self._fix if k not in vehicles]:
            del self._fix[gone]
            self._prev_fix.pop(gone, None)

        # Trains, not vehicles: a three-unit consist is one train. Counted
        # from the in-service records, which are keyed by vehicle.id, so the
        # trip_id collision that used to drop a vehicle cannot happen here.
        running = sorted({r["train"] for r in vehicles.values() if r["in_service"]})

        result = {
            "vehicles": vehicles,
            "running": running,
            "count": len(running),
            "not_in_service": not_in_service,
            "feed_timestamp": feed_ts,
            "last_update": datetime.now().isoformat(timespec="seconds"),
        }
        self._last_good = result
        return result
