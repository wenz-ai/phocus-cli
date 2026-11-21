import copy
import unittest
from local_masks import inspect_masks, linear_args, put_linear


class LinearMaskTests(unittest.TestCase):
    def test_append_and_update_only_one_layer(self):
        old = {"Name": "painted", "LayerType": 0, "BrushData": b"unchanged"}
        saved = copy.deepcopy(old)
        c = {"AdjustmentLayers": {"streamableVersion": 1, "Layers": [old]}}

        def gradient(ev):
            return linear_args([["sky", "0", "0", "1", "1", str(ev)]])

        put_linear(c, gradient(-1))
        put_linear(c, gradient(0.5))
        rows = c["AdjustmentLayers"]["Layers"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], saved)
        self.assertEqual(rows[1]["GradientList"][0]["To"]["PointX"], 0)
        self.assertEqual(inspect_masks(c)[1]["ev"], 0.5)
        self.assertEqual(inspect_masks(c)[1]["linear"][0]["zero"], [1, 1])
        with self.assertRaises(ValueError):
            put_linear(c, [dict(gradient(1)[0], name="painted")])
        self.assertEqual(rows[0], saved)

    def test_bad_inputs(self):
        for args in [
            ["a", 0, 0, 0, 0, 1],
            ["a", 0, 0, 1, 1, 5],
            ["a", -1, 0.4, 1, 1, -1],
            ["a", 0, 0, float("nan"), 1, 1],
            ["", 0, 0, 1, 1, 1],
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                linear_args([args])
