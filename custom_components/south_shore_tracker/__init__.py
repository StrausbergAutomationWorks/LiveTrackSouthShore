"""South Shore Line (NICTD) tracker for Home Assistant.

Live train positions and delays for the South Shore Line, which runs from
Millennium Station in the Chicago Loop out to South Bend, Indiana. Operated by
NICTD rather than Metra, so it is absent from Metra integrations despite
sharing Metra Electric District trackage into the Loop.

Needs no API key: NICTD's realtime feeds are published as public S3 objects.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SouthShoreCoordinator

_LOGGER = logging.getLogger(__name__)

# ! Adding a platform needs a FULL Home Assistant restart, not a config-entry
# reload: Python caches imported modules, so a reload re-runs setup against
# the code already in memory and the new platform simply never appears - no
# error, no log line. See 05_SHARED_LESSONS.md D6a-0c.
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.GEO_LOCATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up South Shore Line Tracker from a config entry."""
    # One coordinator for every platform. It is built here rather than in a
    # platform module so sensor and geo_location share a single poll of the
    # feed instead of one each.
    coordinator = SouthShoreCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change, so a new scan interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)
