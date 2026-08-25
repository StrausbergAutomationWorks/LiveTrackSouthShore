"""Coordinator: fetch NICTD positions + delays and place trains into slots."""

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
    LIVE_TRAIN_SLOTS,
    POSITIONS_URL,
    REQUEST_TIMEOUT,
    TRIP_UPDATES_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class SouthShoreCoordinator(DataUpdateCoordinator):
    """Poll both realtime feeds and expose trains in stable slots."""

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

        # Sticky train-number -> slot mapping. Without stickiness the slot
        # order reshuffles as trains enter and leave service, and map markers
        # jump between entities instead of moving.
        self._slot_by_train: dict[str, int] = {}

        # Previous position per train, so direction can be inferred. The feed
        # reports bearing 0 for every vehicle, so it cannot be read directly.
        self._prev_pos: dict[str, tuple[float, float]] = {}

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
            raise UpdateFailed("positions feed unavailable")
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

        # --- positions ---
        trains: dict[str, dict[str, Any]] = {}
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
            # covers both cases and both should be excluded from the slots.
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
            brg = None
            if train in self._prev_pos:
                brg = self._bearing(self._prev_pos[train], here)
            self._prev_pos[train] = here

            delay_s = delays.get(train)
            trains[train] = {
                "train": train,
                "in_service": in_service,
                "label": label or None,
                "vehicle_id": (v.vehicle.id or "").strip() or None,
                "latitude": here[0],
                "longitude": here[1],
                # Derived, not from the feed - see const.py.
                "bearing": round(brg) if brg is not None else None,
                "delay_min": round(delay_s / 60) if delay_s is not None else None,
                "delay_seconds": delay_s,
                "on_time": (delay_s is not None and abs(delay_s) < 300),
            }

        # drop remembered positions for trains no longer running
        for gone in [t for t in self._prev_pos if t not in trains]:
            del self._prev_pos[gone]

        return {
            "trains": trains,
            "count": len(trains),
            "not_in_service": not_in_service,
            "slots": self._assign_slots(trains),
            "feed_timestamp": int(getattr(pos_feed.header, "timestamp", 0) or 0),
            "last_update": datetime.now().isoformat(timespec="seconds"),
        }

    def _assign_slots(
        self, trains: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any] | None]:
        """Place trains in stable slots; a train keeps its slot for its run."""
        live = set(trains)

        for gone in [t for t in self._slot_by_train if t not in live]:
            del self._slot_by_train[gone]

        taken = set(self._slot_by_train.values())
        for train in sorted(live):
            if train in self._slot_by_train:
                continue
            free = next((i for i in range(LIVE_TRAIN_SLOTS) if i not in taken), None)
            if free is None:
                _LOGGER.warning(
                    "More than %s South Shore trains running; %s not shown. "
                    "LIVE_TRAIN_SLOTS needs raising.",
                    LIVE_TRAIN_SLOTS,
                    train,
                )
                break
            self._slot_by_train[train] = free
            taken.add(free)

        slots: list[dict[str, Any] | None] = [None] * LIVE_TRAIN_SLOTS
        for train, idx in self._slot_by_train.items():
            slots[idx] = trains[train]
        return slots
