"""Record -> attributes mapping and fix tracking. Stdlib only; no Home Assistant.

Run from the repo root:  python -m unittest discover -s tests -v

The two modules are loaded by FILE PATH so the package __init__, which imports
Home Assistant, is never executed.
"""

import importlib.util
import pathlib
import unittest
from datetime import datetime

COMP = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "south_shore_tracker"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"sst_{name}", COMP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


motion = _load("motion")
attributes = _load("attributes")

T0 = 1789880283          # previous fix, epoch s
T1 = 1789880312          # newest fix, 29 s later
A = (41.600000, -87.300000)
B = (41.603000, -87.296000)   # ~470 m NE of A


def _rec(motion_fields):
    rec = {"vehicle_id": "307", "train": "515", "in_service": True,
           "latitude": B[0], "longitude": B[1], "marker_label": "515",
           "delay_min": None}
    rec.update(motion_fields)
    return rec


def _two_fixes(ts0=True, ts1=True):
    fixes, prevs = {}, {}
    motion.track(fixes, prevs, "307", A, T0, ts0)
    return motion.track(fixes, prevs, "307", B, T1, ts1), fixes, prevs


def _instant(s):
    """Parse an ISO string; require an explicit offset."""
    dt = datetime.fromisoformat(s)
    assert dt.utcoffset() is not None, f"no timezone offset in {s!r}"
    return dt


class MappingTests(unittest.TestCase):

    def test_instants_are_iso_with_offset_and_round_trip(self):
        m, _, _ = _two_fixes()
        a = attributes.to_attributes(_rec(m))
        for key, want in (("observed_at", T1), ("last_seen", T1),
                          ("previous_observed_at", T0)):
            self.assertIsInstance(a[key], str, key)
            self.assertEqual(int(_instant(a[key]).timestamp()), want, key)
        self.assertTrue(a["observed_at"].endswith("+00:00"))

    def test_exact_format(self):
        self.assertEqual(attributes.iso_utc(1789880312), "2026-09-20T04:58:32+00:00")

    def test_segment_equals_observed_minus_previous(self):
        m, _, _ = _two_fixes()
        a = attributes.to_attributes(_rec(m))
        self.assertIsInstance(a["segment_duration_s"], int)
        diff = _instant(a["observed_at"]) - _instant(a["previous_observed_at"])
        self.assertEqual(a["segment_duration_s"], int(diff.total_seconds()))
        self.assertEqual(a["segment_duration_s"], T1 - T0)

    def test_no_observed_at_when_vehicle_had_no_timestamp(self):
        m, _, _ = _two_fixes(ts0=True, ts1=False)
        a = attributes.to_attributes(_rec(m))
        for key in ("observed_at", "last_seen", "previous_observed_at",
                    "previous_latitude", "previous_longitude", "segment_duration_s"):
            self.assertNotIn(key, a, key)
        # Position-only derivation is unaffected by the missing time.
        self.assertIn("course_deg", a)

    def test_no_segment_when_the_PREVIOUS_fix_had_no_timestamp(self):
        m, _, _ = _two_fixes(ts0=False, ts1=True)
        a = attributes.to_attributes(_rec(m))
        self.assertIn("observed_at", a)
        for key in ("previous_observed_at", "previous_latitude",
                    "previous_longitude", "segment_duration_s"):
            self.assertNotIn(key, a, key)

    def test_first_sighting_has_no_previous(self):
        fixes, prevs = {}, {}
        m = motion.track(fixes, prevs, "307", A, T0, True)
        a = attributes.to_attributes(_rec(m))
        self.assertIn("observed_at", a)
        for key in ("previous_observed_at", "previous_latitude",
                    "previous_longitude", "segment_duration_s", "course_deg"):
            self.assertNotIn(key, a, key)

    def test_no_numeric_instants_anywhere(self):
        m, _, _ = _two_fixes()
        a = attributes.to_attributes(_rec(m))
        for key in ("observed_at", "last_seen", "previous_observed_at"):
            self.assertNotIsInstance(a[key], (int, float), key)


class DuplicatePollTests(unittest.TestCase):
    """06_MAP_CONTRACT.md D3c-iii must survive the change."""

    def test_duplicate_poll_does_not_advance_previous(self):
        m1, fixes, prevs = _two_fixes()
        prev_before = prevs["307"]
        m2 = motion.track(fixes, prevs, "307", B, T1, True)   # same fix again
        self.assertEqual(prevs["307"], prev_before)
        self.assertEqual(m2, m1)
        a = attributes.to_attributes(_rec(m2))
        self.assertEqual(a["segment_duration_s"], T1 - T0)

    def test_new_fix_advances(self):
        _, fixes, prevs = _two_fixes()
        C = (41.606000, -87.292000)
        m3 = motion.track(fixes, prevs, "307", C, T1 + 30, True)
        self.assertEqual(m3["previous_observed_at"], T1)
        self.assertEqual(m3["segment_duration_s"], 30)

    def test_implausible_gap_has_no_segment(self):
        fixes, prevs = {}, {}
        motion.track(fixes, prevs, "307", A, T0, True)
        m = motion.track(fixes, prevs, "307", B, T0 + motion.MAX_SEGMENT_S + 1, True)
        self.assertIn("observed_at", m)
        self.assertNotIn("segment_duration_s", m)

    def test_forget_absent(self):
        _, fixes, prevs = _two_fixes()
        motion.forget_absent(fixes, prevs, {})
        self.assertEqual((fixes, prevs), ({}, {}))


if __name__ == "__main__":
    unittest.main()
