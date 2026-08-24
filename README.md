# South Shore Line Train Tracker

Home Assistant integration for live train positions and delays on the
**South Shore Line** (NICTD) — Millennium Station in the Chicago Loop out to
South Bend, Indiana.

Operated by NICTD rather than Metra, so it is absent from Metra integrations
despite sharing Metra Electric District trackage into the Loop.

## Why this exists

NICTD publishes GTFS-Realtime feeds as public S3 objects — **no API key, no
licence agreement, no registration**. As far as I can tell nothing consumed
them for Home Assistant.

## What you get

* **16 slot entities**, each holding one train currently running. Sticky
  assignment: a train keeps its slot for its whole run, so map markers move
  smoothly instead of jumping between entities.
* `latitude` / `longitude` attributes, so Home Assistant's map plots trains
  with no card configuration.
* `delay_min` per train, joined from the trip-updates feed.
* A **running-count** sensor with the worst current delay and a list of
  trains five or more minutes late.

## Feed quirks worth knowing

The feed is GTFS-RT but non-standard in three ways:

| Field | Reality |
|---|---|
| `route_id` | Always empty. NICTD runs one line, so everything in the feed is in scope. |
| `trip_id` | The bare train number (`515`), not a GTFS trip_id. Will not join a static schedule. |
| `bearing` | Always `0`. This integration derives direction from successive positions instead. |

There is also no `stop_id` and no absolute arrival times — only `stop_sequence`
and a delay offset. So "how late is it" works; "when does it reach Millennium"
would need a static schedule, and no current NICTD GTFS static source appears
to exist. TransitFeeds is deprecated and GTFS Data Exchange's NICTD feed was
last updated in 2010.

The 16-slot pool is an **estimate**, not measured — peak concurrency is unknown
without a static schedule. Five trains were running at midnight on a Sunday, so
the true weekday peak may well be higher. The count sensor and a log warning
will show if the pool is ever exhausted.

## Install

Copy `custom_components/south_shore_tracker/` into your Home Assistant `config`
directory and restart, then add the integration from
**Settings → Devices & Services → Add Integration → South Shore Line Train
Tracker**. The only setting is the poll interval.

## Author

Built by **Strausberg Automation Works**.

Related work — additive contributions to existing Home Assistant integrations:

* [flights_above](https://github.com/LeeS773-prog/flights_above) — a third ADS-B
  position source plus ICAO operator and aircraft-type resolution
* [Metra-Tracker-Lee](https://github.com/LeeS773-prog/Metra-Tracker-Lee) — live
  GTFS-Realtime vehicle positions for Metra

## Attribution

Live data from NICTD / South Shore Line via ETA SPOT (mysouthshoreline.com).
Not affiliated with, endorsed by, or supported by NICTD or Metra.

## Licence

MIT.
