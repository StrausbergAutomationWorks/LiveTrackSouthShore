# South Shore Line Tracker

Home Assistant integration for live train positions and delays on the
**South Shore Line** (NICTD) â€” Millennium Station in the Chicago Loop out to
South Bend, Indiana.

Operated by NICTD rather than Metra, so it is absent from Metra integrations
despite sharing Metra Electric District trackage into the Loop.

## Why this exists

NICTD publishes GTFS-Realtime feeds as public S3 objects â€” **no API key, no
licence agreement, no registration**. Nothing consumed them for Home Assistant.

## What you get

* **16 slot entities**, each holding one train currently running. Sticky
  assignment: a train keeps its slot for its whole run, so map markers move
  smoothly instead of jumping between entities.
* `latitude` / `longitude` attributes, so Home Assistant's map plots trains
  with no card configuration.
* `delay_min` per train, from the trip-updates feed.
* A **running-count** sensor with the worst current delay and a list of
  trains five or more minutes late.

## Feed quirks worth knowing

The feed is GTFS-RT but non-standard in three ways:

| Field | Reality |
|---|---|
| `route_id` | Always empty. NICTD runs one line, so everything in the feed is in scope. |
| `trip_id` | The bare train number (`515`), not a GTFS trip_id. Will not join a static schedule. |
| `bearing` | Always `0`. This integration derives direction from successive positions instead. |

There is also no `stop_id` and no absolute arrival times â€” only `stop_sequence`
and a delay offset. So "how late is it" works; "when does it reach Millennium"
would need a static schedule, and no current NICTD GTFS static source appears
to exist.

## Install

Copy `custom_components/south_shore_tracker/` into your HA `config` directory
and restart, then add the integration from Settings â†’ Devices & Services.
The only setting is the poll interval.

## Attribution

Live data from NICTD / South Shore Line via ETA SPOT (mysouthshoreline.com).
Not affiliated with or endorsed by NICTD.
