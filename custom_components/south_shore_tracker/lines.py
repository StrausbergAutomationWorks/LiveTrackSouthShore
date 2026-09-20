"""Which South Shore line a train is on, and its marker colours. No HA imports.

Measured 2026-09-20 from the NICTD April 2026 timetable (SSOT, "Line from
train number"): the printed key colours every train, and on all 139 trains
the colour matches this rule with 0 misses and no number on both lines:

    Monon Corridor   300-399, or 1000 and above
    Lakeshore        every other number

! This is NICTD's numbering in that timetable, not a published rule.
Re-check it when a new timetable comes out.

! Key it on the feed's trip_id, NEVER the label. A Monon train laying over
reported label "NIS" with trip_id "1601", then label "1601" once under way.
"""

from __future__ import annotations

LAKESHORE = "lakeshore"
MONON = "monon"

# Colours are this integration's own decision (06_MAP_CONTRACT.md D4a), set by
# Lee 2026-09-20: Lakeshore fill orange with dark red text, Monon the reverse.
# `#` plus six hex digits only (D4a rule 2).
MARKER_COLOR = {LAKESHORE: "#EF8322", MONON: "#7F281F"}
LABEL_COLOR = {LAKESHORE: "#7F281F", MONON: "#EF8322"}

# Outlines, set by Lee 2026-09-20 after seeing the render (D4a rule 6b). A line
# ABSENT from a table emits no key, and the card draws its default dark
# outline. Never add an entry just to restate that default.
#   Lakeshore label: outlined in the fill's own orange. The #7F281F label read
#     near-black inside a dark outline, and the label overflows the 28 px disc;
#     an orange outline reads as the disc continuing under the text.
#   Monon arrow: outlined white. It is filled #7F281F (the marker's fill, the
#     card's default), and dark red with a dark outline was faint on the map.
# marker_arrow_color is deliberately NOT emitted: the default, the marker's
# own fill, is what Lee saw and kept.
LABEL_OUTLINE_COLOR = {LAKESHORE: "#EF8322"}
ARROW_OUTLINE_COLOR = {MONON: "#FFFFFF"}


def styling(line: str | None) -> dict[str, str]:
    """Every colour key for a line, each only when this integration sets one.

    No line (the trip id is not a train number) -> {} (D4a rule 3).
    """
    if line is None:
        return {}
    out = {"marker_color": MARKER_COLOR[line],
           "marker_label_color": LABEL_COLOR[line]}
    if line in LABEL_OUTLINE_COLOR:
        out["marker_label_outline_color"] = LABEL_OUTLINE_COLOR[line]
    if line in ARROW_OUTLINE_COLOR:
        out["marker_arrow_outline_color"] = ARROW_OUTLINE_COLOR[line]
    return out


def line_of(trip_id: str | None) -> str | None:
    """'monon', 'lakeshore', or None when the trip id is not a train number."""
    s = (trip_id or "").strip()
    if not s.isdigit():
        return None
    n = int(s)
    return MONON if (n >= 1000 or 300 <= n <= 399) else LAKESHORE
