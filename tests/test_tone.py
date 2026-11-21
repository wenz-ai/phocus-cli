import copy
import unittest

from tone_controls import (
    BAND_KEYS,
    GAMMA,
    apply_bands,
    apply_levels,
    bands_args,
    inspect_bands,
    inspect_levels,
    levels_args,
)


class ToneTests(unittest.TestCase):
    def test_rgb_applied_before_channel_override(self):
        c = {"Shadow": [0] * 4, "Highlight": [16320] * 4, **dict.fromkeys(GAMMA, 2.0)}
        levels = levels_args([["red", "3", "1.2", "247"], ["rgb", "12", ".9", "230"]])
        apply_levels(c, levels)
        self.assertEqual(c["Shadow"], [768, 192, 768, 768])
        self.assertEqual(
            inspect_levels(c),
            {
                "rgb": [12, 0.9, 230],
                "red": [3, 1.2, 247],
                "green": [12, 0.9, 230],
                "blue": [12, 0.9, 230],
            },
        )
        apply_levels(c, {"green": [2, 1.5, 240]})
        self.assertEqual(inspect_levels(c)["blue"], [12, 0.9, 230])

    def test_validate_before_writes(self):
        for invalid in [
            [["rgb", "180", "1", "180"]],
            [["rgb", "0", "nan", "255"]],
            [["red", "2.2", "1", "255"]],
        ]:
            with self.assertRaises(ValueError):
                levels_args(invalid)
        for h in ("360", "-2", "nan", "no-such-color"):
            with self.assertRaises(ValueError):
                bands_args([[h, 30, 0, 1, 0]])
        with self.assertRaises(ValueError):
            bands_args([["0", 30, 0, 1, 0], ["red", 30, 5, 1, 0]])

    def test_native_point_roundtrip_and_edit_preserves_other_bands(self):
        c = {k: [] for k in BAND_KEYS}
        apply_bands(
            c, bands_args([["48.12", 30, 18, 0.6, 12], ["blue", 25, -15, 1.5, -6]])
        )
        self.assertAlmostEqual(c["SelectiveDstL"][0], 0.3)
        self.assertAlmostEqual(c["SelectiveDstH"][0], 66.12)
        self.assertEqual(c["SelectiveDstS"][0], 12)
        self.assertEqual(
            inspect_bands(c)[1],
            {"hue": 240, "width": 25, "shift": -15, "saturation": 1.5, "lightness": -6},
        )
        saved = copy.deepcopy(c)
        apply_bands(c, bands_args([["48.120001", 24, 0, 1, 0]]))
        for key in BAND_KEYS:
            self.assertEqual(c[key][1], saved[key][1])
        self.assertEqual(len(c[BAND_KEYS[0]]), 2)
        apply_bands(c, bands_args([["red", 25, -35, 1, 0]]), clear=True)
        self.assertEqual(inspect_bands(c)[0]["shift"], -35)
        apply_bands(c, [], clear=True)
        self.assertEqual(inspect_bands(c), [])
        with self.assertRaises(ValueError):
            apply_bands({"SelectiveSrcH": [1]}, [])
