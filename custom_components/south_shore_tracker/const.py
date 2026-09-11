"""Constants for the South Shore Line (NICTD) tracker."""

DOMAIN = "south_shore_tracker"

CONF_COUNT = "count"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_NAME = "South Shore Line Train Tracker"
DEFAULT_SCAN_INTERVAL = 30  # seconds; the feed republishes roughly this often
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

# ! RETIRED 2026-09-11: LIVE_TRAIN_SLOTS and the 28 slot sensors are gone.
#
# The slot pool existed because Home Assistant had no way to show a varying
# number of markers, so a fixed pool of entities was allocated and trains were
# assigned into it. The geo_location platform creates one entity per vehicle
# as it appears, so the pool has nothing left to do.
#
# It also carried a bug that dies with it: slots were keyed on trip_id, and
# two trailing NIS units can share one. Measured 2026-09-06 - 12 vehicles in
# the feed but only 11 distinct trip_ids - so one vehicle was silently
# dropped. geo_location keys on vehicle.id, which is set and unique on every
# vehicle including trailing units.
#
# Backlog item 12 asked for the real peak to be measured so the estimate of
# 28 could be corrected. That question is moot: there is no longer a number
# to size.

# GTFS-Realtime feeds. Published as plain S3 objects by ETA SPOT on NICTD's
# behalf - no API key, no licence agreement, no registration.
POSITIONS_URL = (
    "https://s3.amazonaws.com/etatransit.gtfs/"
    "southshore.etaspot.net/position_updates.pb"
)
TRIP_UPDATES_URL = (
    "https://s3.amazonaws.com/etatransit.gtfs/"
    "southshore.etaspot.net/trip_updates.pb"
)

# ! The feed is GTFS-RT but NON-STANDARD in three ways that matter. Verified
# against the live feed 2026-08-23:
#
#   route_id  is ALWAYS EMPTY. Do not filter on it - NICTD runs a single
#             line, so every vehicle in the feed is ours.
#   trip_id   is the bare train number ("515"), NOT a GTFS trip_id. It will
#             not join against a static schedule.
#   bearing   is ALWAYS 0. Direction must be inferred from successive
#             positions, not read from the feed.
#
# The two feeds DO join on trip_id: positions carries trip_id/label "515"
# while trip_updates carries trip_id "515" with vehicle.id "310", matching
# the "vehicle_position_310" entity id.

ATTRIBUTION = (
    "Live data from NICTD / South Shore Line via ETA SPOT "
    "(mysouthshoreline.com)"
)

USER_AGENT = "home-assistant-south-shore-tracker/1.0"
REQUEST_TIMEOUT = 20  # seconds

# How many consecutive fetch failures to ride out before the coordinator
# reports failure and entities go unavailable. The feed is normally fast and
# reliable (40 consecutive requests on 2026-08-25: 0 failures, median 0.15 s),
# but 9 transient failures were logged across one day - almost certainly brief
# network drops on the host rather than the feed itself. Blanking every marker
# for a single blip is worse than briefly serving a slightly stale position,
# whose age is visible in feed_timestamp.
MAX_TRANSIENT_FAILURES = 2
