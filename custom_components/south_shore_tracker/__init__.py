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

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up South Shore Line Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})
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
