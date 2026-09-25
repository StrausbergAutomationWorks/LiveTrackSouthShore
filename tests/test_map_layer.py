"""Map layer and the retired z_index_offset (backlog 258, 06_MAP_CONTRACT.md D10/D11).

Run from the repo root:  python -m unittest discover -s tests -v
Loads attributes.py by file path so Home Assistant is never imported.
"""

import importlib.util
import pathlib
import unittest

COMP = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "south_shore_tracker"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"sst_ml_{name}", COMP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


attributes = _load("attributes")

# D10's list, verbatim. Nothing outside it may be emitted.
D10_LAYERS = {"fixed", "water", "rail", "air_low", "air"}
# D11's keys. The GTFS-RT feed states none of them, so object_ids is absent.
D11_KEYS = {"mmsi", "imo", "icao24", "registration"}

IN_SERVICE = {"vehicle_id": "1269", "train": "115", "in_service": True,
              "latitude": 41.6, "longitude": -87.5, "marker_label": "115",
              "line": "lakeshore", "marker_color": "#EF8322"}
NIS = {"vehicle_id": "304", "train": "NIS", "in_service": False,
       "latitude": 41.6, "longitude": -87.5, "marker_label": "NIS 304"}
NO_TRIP = {"vehicle_id": "13", "train": "", "in_service": False,
           "latitude": 41.6, "longitude": -87.5, "marker_label": "NIS 13"}


class MapLayerTests(unittest.TestCase):

    def test_every_unit_is_rail(self):
        # NIS units too: they are rail vehicles on real track (D8).
        for rec in (IN_SERVICE, NIS, NO_TRIP):
            a = attributes.to_attributes(dict(rec))
            self.assertEqual(a.get("map_layer"), "rail", rec["marker_label"])

    def test_layer_is_a_d10_name_and_a_plain_string(self):
        a = attributes.to_attributes(dict(IN_SERVICE))
        self.assertIs(type(a["map_layer"]), str)
        self.assertIn(a["map_layer"], D10_LAYERS)

    def test_record_cannot_override_the_layer(self):
        rec = dict(IN_SERVICE, map_layer="fixed", z_index_offset=40000,
                   object_ids={"mmsi": "123456789"})
        a = attributes.to_attributes(rec)
        self.assertEqual(a["map_layer"], "rail")
        self.assertNotIn("z_index_offset", a)
        self.assertNotIn("object_ids", a)


class RetiredKeyTests(unittest.TestCase):

    def test_no_z_index_offset_attribute(self):
        # D10: the numeric attribute is retired; the card never read it.
        for rec in (IN_SERVICE, NIS, NO_TRIP):
            self.assertNotIn("z_index_offset", attributes.to_attributes(dict(rec)))

    def test_no_dead_constant(self):
        self.assertFalse(hasattr(attributes, "Z_INDEX_OFFSET"))

    def test_no_object_ids(self):
        # D11: only listed keys, only as the source states them. A vehicle or
        # trip id is none of them, so the key is left out entirely (D0).
        for rec in (IN_SERVICE, NIS, NO_TRIP):
            a = attributes.to_attributes(dict(rec))
            self.assertNotIn("object_ids", a)
            self.assertFalse(D11_KEYS & set(a), sorted(D11_KEYS & set(a)))


if __name__ == "__main__":
    unittest.main()
