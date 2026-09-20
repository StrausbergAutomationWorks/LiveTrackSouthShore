"""Line from train number, marker colours, and the held arrow bearing.

Run from the repo root:  python -m unittest discover -s tests -v
Modules are loaded by file path so the package __init__ (Home Assistant) is
never executed.
"""

import importlib.util
import pathlib
import re
import unittest

COMP = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "south_shore_tracker"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"sst_{name}", COMP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lines = _load("lines")
motion = _load("motion")
attributes = _load("attributes")

# Every train in the NICTD April 2026 timetable, classed by the fill colour of
# its header cell read from the PDF (red = Monon, orange = Lakeshore), 2026-09-20.
MONON = [301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 1000, 1001,
         1011, 1014, 1016, 1018, 1022, 1024, 1032, 1033, 1035, 1060, 1062, 1064,
         1101, 1105, 1109, 1111, 1113, 1120, 1122, 1126, 1131, 1133, 1207, 1226,
         1501, 1502, 1503, 1504, 1505, 1506, 1507, 1508, 1509, 1510, 1511, 1512,
         1513, 1515, 1517, 1600, 1601, 1609, 1610, 1612]
LAKESHORE = [7, 10, 11, 16, 17, 22, 24, 25, 30, 32, 33, 35, 101, 102, 104, 105,
             106, 108, 109, 110, 111, 112, 113, 114, 115, 117, 118, 119, 120, 121,
             122, 123, 126, 127, 128, 129, 130, 131, 133, 201, 203, 205, 207, 209,
             214, 218, 222, 224, 225, 226, 228, 232, 400, 401, 403, 405, 430, 432,
             502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 515, 517,
             600, 601, 608, 609, 610, 612, 701, 703, 705]
HEX6 = re.compile(r"^#[0-9A-Fa-f]{6}$")


class LineTests(unittest.TestCase):

    def test_every_timetable_train(self):
        self.assertEqual(len(MONON) + len(LAKESHORE), 139)
        for n in MONON:
            self.assertEqual(lines.line_of(str(n)), lines.MONON, n)
        for n in LAKESHORE:
            self.assertEqual(lines.line_of(str(n)), lines.LAKESHORE, n)

    def test_not_a_train_number(self):
        for t in (None, "", "NIS", " ", "515A", "-1"):
            self.assertIsNone(lines.line_of(t), repr(t))
        self.assertEqual(lines.line_of(" 1601 "), lines.MONON)

    def test_colours_are_d4a_form_and_swapped(self):
        for line in (lines.LAKESHORE, lines.MONON):
            self.assertRegex(lines.MARKER_COLOR[line], HEX6)
            self.assertRegex(lines.LABEL_COLOR[line], HEX6)
        self.assertEqual(lines.MARKER_COLOR[lines.LAKESHORE], "#EF8322")
        self.assertEqual(lines.LABEL_COLOR[lines.LAKESHORE], "#7F281F")
        self.assertEqual(lines.MARKER_COLOR[lines.MONON], lines.LABEL_COLOR[lines.LAKESHORE])
        self.assertEqual(lines.LABEL_COLOR[lines.MONON], lines.MARKER_COLOR[lines.LAKESHORE])


COLOUR_KEYS = ("marker_color", "marker_label_color", "marker_label_outline_color",
               "marker_arrow_color", "marker_arrow_outline_color")


def _published(trip_id):
    """What a unit on this trip publishes, through the coordinator's own path:
    line_of -> styling onto the record -> attributes.to_attributes."""
    rec = {"vehicle_id": "13", "train": trip_id or "NIS", "in_service": True,
           "latitude": 41.6, "longitude": -87.5, "marker_label": "x"}
    line = lines.line_of(trip_id)
    if line is not None:
        rec["line"] = line
    rec.update(lines.styling(line))
    return attributes.to_attributes(rec)


class OutlineTests(unittest.TestCase):
    """Lee 2026-09-20, D4a rule 6b: every label outlined in its marker's fill;
    every arrow filled with the marker's fill (card default, so no
    marker_arrow_color) and outlined in the OTHER line colour."""

    def test_every_lakeshore_number(self):
        for n in LAKESHORE:
            a = _published(str(n))
            self.assertEqual(a["marker_label_outline_color"], "#EF8322", n)
            self.assertEqual(a["marker_arrow_outline_color"], "#7F281F", n)
            self.assertNotIn("marker_arrow_color", a, n)

    def test_every_monon_number(self):
        for n in MONON:
            a = _published(str(n))
            self.assertEqual(a["marker_label_outline_color"], "#7F281F", n)
            self.assertEqual(a["marker_arrow_outline_color"], "#EF8322", n)
            self.assertNotIn("marker_arrow_color", a, n)

    def test_outline_rules_as_lee_stated_them(self):
        # Label outline = the fill. Arrow = the fill (not emitted), so its
        # outline is whichever line colour the arrow is not.
        for n in MONON + LAKESHORE:
            a = _published(str(n))
            self.assertEqual(a["marker_label_outline_color"], a["marker_color"], n)
            self.assertNotEqual(a["marker_arrow_outline_color"], a["marker_color"], n)
            self.assertIn(a["marker_arrow_outline_color"],
                          set(lines.MARKER_COLOR.values()), n)

    def test_no_train_number_no_colour_keys(self):
        for t in (None, "", "NIS", "515A"):
            a = _published(t)
            self.assertNotIn("line", a, repr(t))
            for k in COLOUR_KEYS:
                self.assertNotIn(k, a, (repr(t), k))

    def test_styling_table_restates_no_default(self):
        # Checked at the source as well as at publication: attributes.py's
        # passthrough is a whitelist and would hide an extra key in lines.py.
        self.assertEqual(lines.styling(None), {})
        want = {"marker_color", "marker_label_color",
                "marker_label_outline_color", "marker_arrow_outline_color"}
        self.assertEqual(set(lines.styling(lines.LAKESHORE)), want)
        self.assertEqual(set(lines.styling(lines.MONON)), want)

    def test_every_value_is_d4a_form(self):
        for n in MONON + LAKESHORE:
            a = _published(str(n))
            present = [k for k in COLOUR_KEYS if k in a]
            self.assertEqual(len(present), 4, n)
            for k in present:
                self.assertRegex(a[k], HEX6, (n, k))


class HeldBearingTests(unittest.TestCase):

    A = (41.600000, -87.300000)
    B = (41.603000, -87.296000)
    C = (41.606000, -87.292000)

    def _poll(self, st, here, t):
        fixes, prevs, held = st
        m = motion.track(fixes, prevs, "13", here, t, True)
        m.update(motion.rotation(held, "13", m.get("course_deg")))
        return m

    def test_moving_then_stopped_holds_last_bearing(self):
        st = ({}, {}, {})
        self._poll(st, self.A, 100)
        moving = self._poll(st, self.B, 130)
        self.assertEqual(moving["icon_rotation_basis"], "course")
        stopped = self._poll(st, self.B, 160)       # new time, same place
        self.assertNotIn("course_deg", stopped)     # D3c-iii omission kept
        self.assertEqual(stopped["icon_rotation_basis"], "held")
        self.assertEqual(stopped["icon_rotation_deg"], moving["icon_rotation_deg"])
        again = self._poll(st, self.C, 190)          # moves again
        self.assertEqual(again["icon_rotation_basis"], "course")

    def test_first_seen_standing_has_no_bearing(self):
        st = ({}, {}, {})
        self._poll(st, self.A, 100)
        m = self._poll(st, self.A, 130)
        self.assertNotIn("icon_rotation_deg", m)
        self.assertNotIn("icon_rotation_basis", m)

    def test_forget_absent_drops_held(self):
        st = ({}, {}, {})
        self._poll(st, self.A, 100)
        self._poll(st, self.B, 130)
        motion.forget_absent(st[0], st[1], {}, st[2])
        self.assertEqual(st, ({}, {}, {}))


class AttributePassthroughTests(unittest.TestCase):

    def test_colour_line_and_rotation_reach_attributes(self):
        rec = {"vehicle_id": "13", "train": "1601", "in_service": True,
               "latitude": 41.6, "longitude": -87.5, "marker_label": "1601",
               "line": "monon", "marker_color": "#7F281F",
               "marker_label_color": "#EF8322", "icon_rotation_deg": 181.2,
               "icon_rotation_basis": "held"}
        a = attributes.to_attributes(rec)
        for k in ("line", "marker_color", "marker_label_color",
                  "icon_rotation_deg", "icon_rotation_basis"):
            self.assertEqual(a[k], rec[k], k)

    def test_no_line_means_no_colour_keys(self):
        rec = {"vehicle_id": "13", "train": "NIS", "in_service": False,
               "latitude": 41.6, "longitude": -87.5, "marker_label": "NIS 13"}
        a = attributes.to_attributes(rec)
        for k in ("line", "marker_color", "marker_label_color"):
            self.assertNotIn(k, a)


if __name__ == "__main__":
    unittest.main()
