import copy
import unittest
from local_masks import inspect_masks, linear_args, radial_args, put_masks


class LinearMaskTests(unittest.TestCase):
    def test_append_and_update_only_one_layer(self):
        old = {"Name": "painted", "LayerType": 0, "BrushData": b"unchanged"}
        saved = copy.deepcopy(old)
        c = {"AdjustmentLayers": {"streamableVersion": 1, "Layers": [old]}}

        def gradient(ev):
            return linear_args([["sky", "0", "0", "1", "1", str(ev)]])

        put_masks(c, gradient(-1))
        put_masks(c, gradient(0.5))
        rows = c["AdjustmentLayers"]["Layers"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], saved)
        self.assertEqual(rows[1]["GradientList"][0]["To"]["PointX"], 0)
        self.assertEqual(inspect_masks(c)[1]["ev"], 0.5)
        self.assertEqual(inspect_masks(c)[1]["linear"][0]["zero"], [1, 1])
        with self.assertRaises(ValueError):
            put_masks(c, [dict(gradient(1)[0], name="painted")])
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

    def test_radial_update_preserves_other_layers_and_validates_bounds(self):
        row = ["face", 0.3, 0.5, 0.2, 0.1, 90, 0.4, "outside", 0.5]
        recipe = radial_args([row])
        c = {"AdjustmentLayers": {"streamableVersion": 1}}
        put_masks(c, recipe)
        ellipse = inspect_masks(c)[0]["radial"][0]
        self.assertEqual(
            ellipse, {k: v for k, v in recipe[0].items() if k not in {"name", "ev"}}
        )
        put_masks(c, radial_args([row[:-1] + [-1]]))
        self.assertEqual(len(inspect_masks(c)), 1)
        self.assertEqual(inspect_masks(c)[0]["ev"], -1)
        with self.assertRaises(ValueError):
            put_masks(c, linear_args([["face", 0, 0, 1, 1, 1]]))
        for index, bad in ((2, float("nan")), (3, 0), (6, 1.1), (7, "edge")):
            invalid = row.copy()
            invalid[index] = bad
            with self.assertRaises(ValueError):
                radial_args([invalid])

    def test_local_edits_leave_mask_geometry_and_other_controls_in_place(self):
        from local_masks import apply_layer_adjustments, layer_adjustments

        c = {"AdjustmentLayers": {"streamableVersion": 1}}
        mask = radial_args([["face", 0.5, 0.5, 0.2, 0.1, 0, 0.2, "inside", 0.5]])
        put_masks(c, mask)
        apply_layer_adjustments(
            c,
            layer_adjustments(
                [["face", "temperature", 13], ["face", "highlights", 27]]
            ),
        )
        put_masks(c, mask)
        self.assertEqual(
            inspect_masks(c)[0]["adjustments"], {"temperature": 13, "highlights": 27}
        )
        with self.assertRaises(ValueError):
            layer_adjustments([["face", "temperature", 200]])
        with self.assertRaises(ValueError):
            apply_layer_adjustments(c, {"missing": {"clarity": 9}})
