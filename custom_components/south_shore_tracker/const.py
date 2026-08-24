"""Constants for the South Shore Line (NICTD) tracker."""

DOMAIN = "south_shore_tracker"

CONF_COUNT = "count"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_NAME = "South Shore Line"
DEFAULT_SCAN_INTERVAL = 30  # seconds; the feed republishes roughly this often
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

# Live-position slots.
#
# ! ESTIMATE, NOT MEASURED - unlike the Metra tracker, whose pool was derived
# from Metra's own GTFS static schedule. No current NICTD static GTFS source
# could be found (TransitFeeds is deprecated; GTFS Data Exchange's NICTD feed
# was last updated in 2010), so peak concurrency is unknown.
#
# Reasoning behind 16: the line runs ~21 stations over 99 miles, end-to-end
# journeys take roughly 2.5 h, and weekday service is in the region of 40-45
# trains. That suggests something under 12 concurrent at peak. 16 leaves room,
# and empty slots cost nothing.
#
# TODO: measure actual peak over a full weekday and correct this, the way
# UP-W's 18 was arrived at.
LIVE_TRAIN_SLOTS = 16

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
