"""Offline regression checks. All inputs are synthetic, no running Phocus needed."""

import plistlib
import runpy
import tempfile
import unittest
from pathlib import Path

api = runpy.run_path(str(Path(__file__).with_name("phocus")))


class SidecarTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.raw = self.root / "sample.3FR"
        self.raw.write_bytes(b"placeholder")
        self.file = api["sidecar"](self.raw)
        self.content = plistlib.dumps(
            {
                "Version": 31,
                "CurrentIx": 1,
                "Unknown": b"keep",
                "ImageSettings": [
                    {"ImageCorrection": {"EV": 1.0}},
                    {
                        "ImageCorrection": {
                            "streamableVersion": 11,
                            "EV": 1.0,
                            "ApplyEV": False,
                        }
                    },
                ],
            }
        )
        self.file.write_bytes(self.content)

    def test_edit_copies_active_version_and_retains_unknown_fields(self):
        result = api["variant"](self.raw, self.root, {"exposure": 1})
        data = plistlib.loads(Path(result["sidecar"]).read_bytes())
        self.assertEqual(data["Unknown"], b"keep")
        self.assertEqual(data["ImageSettings"][0]["ImageCorrection"], {"EV": 1.0})
        self.assertEqual(data["ImageSettings"][1]["ImageCorrection"]["EV"], 2.0)
        self.assertTrue(data["ImageSettings"][1]["ImageCorrection"]["ApplyEV"])
        self.assertEqual(self.file.read_bytes(), self.content)

    def test_incompatible_version_does_not_publish_variant(self):
        data = plistlib.loads(self.content)
        data["Version"] = 32
        self.file.write_bytes(plistlib.dumps(data))
        with self.assertRaises(ValueError):
            api["variant"](self.raw, self.root, {"exposure": 1})
        self.assertEqual(list(self.root.glob("variant-*")), [])

    def test_unusable_adjustments_rejected(self):
        for item in ["exposure=nan", "exposure=5", "clarity=2.5", "mystery=0"]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                api["edits"]([item], api["FIELDS"])

    def test_disabled_watcher_times_out_with_recoverable_job(self):
        watch = self.root / "watch"
        spool = self.root / "spool"
        watch.mkdir()
        spool.mkdir()
        with self.assertRaisesRegex(ValueError, "任务副本保留"):
            api["hot_pass"](self.raw, watch, spool, {"exposure": 1}, 0)
        copies = list(watch.glob("*.3FR"))
        self.assertEqual(len(copies), 1)
        self.assertTrue(api["sidecar"](copies[0]).is_file())

    def test_every_control_validates_both_endpoints(self):
        for name, (_, lo, hi, _) in api["FIELDS"].items():
            for val in (lo, hi):
                with self.subTest(name=name, value=val):
                    self.assertEqual(
                        api["edits"]([f"{name}={val}"], api["FIELDS"]), {name: val}
                    )
            for val in (lo - 1, hi + 1):
                with self.subTest(name=name, value=val), self.assertRaises(ValueError):
                    api["edits"]([f"{name}={val}"], api["FIELDS"])

    def test_geometry_on_copy_preserves_existing_description_fields(self):
        data = plistlib.loads(self.content)
        desc = {
            "Rotation": 0.0,
            "RelativeCrop": {
                "Left": 0.0,
                "Top": 0.0,
                "Right": 1.0,
                "Bottom": 1.0,
                "streamableVersion": 1,
            },
            "Zoom": 100.0,
        }
        data["ImageSettings"][1]["ImageDescription"] = desc
        self.file.write_bytes(plistlib.dumps(data))
        result = api["variant"](
            self.raw, self.root, {"crop": [0.1, 0.2, 0.7, 0.8], "rotation": 90}
        )
        saved = plistlib.loads(Path(result["sidecar"]).read_bytes())["ImageSettings"][
            1
        ]["ImageDescription"]
        self.assertEqual(saved["Zoom"], 100)
        self.assertEqual(saved["Rotation"], 90)
        self.assertEqual(saved["RelativeCrop"]["Right"], 0.7)
        self.assertEqual(saved["RelativeCrop"]["streamableVersion"], 1)
        self.assertEqual(
            plistlib.loads(self.file.read_bytes())["ImageSettings"][1][
                "ImageDescription"
            ],
            desc,
        )

    def test_invalid_crop_fails_before_writing(self):
        import argparse

        for crop in [
            [0, 0, 0, 1],
            [0, 0.8, 0.8, 0.3],
            [-1, 0, 1, 1],
            [0, 0, float("nan"), 1],
        ]:
            with self.assertRaises(ValueError):
                api["adjustment_args"](
                    argparse.Namespace(set=[], crop=crop, rotate=None)
                )

    def test_hnnr_rejects_nonempty_queue_before_accessing_ui(self):
        self.assertTrue(self.raw.exists())
        with self.assertRaisesRegex(ValueError, "空的专用队列"):
            api["hnnr"](self.raw, self.root, self.root.parent, "purity", 30)

    def test_curve_updates_only_requested_channel(self):
        identity = {
            "Points": [{"X": 0, "Y": 0, "DY": 1}, {"X": 255, "Y": 255, "DY": 1}],
            "unknown": 7,
        }
        data = plistlib.loads(self.content)
        data["ImageSettings"][1]["ImageCorrection"].update(
            ApplyCurves=False, Gradations=[identity.copy() for _ in range(8)]
        )
        self.file.write_bytes(plistlib.dumps(data))
        curves = api["curve_args"]([["green", "0:0", "128:175", "255:255"]])
        target = api["variant"](self.raw, self.root, {"curves": curves})
        _, applied = api["load_settings"](Path(target["raw"]))
        self.assertTrue(applied["ApplyCurves"])
        self.assertEqual(
            applied["Gradations"][2]["Points"][1], {"X": 128, "Y": 175, "DY": 1}
        )
        self.assertEqual(applied["Gradations"][2]["unknown"], 7)
        self.assertEqual(applied["Gradations"][3], identity)
        _, original = api["load_settings"](self.raw)
        self.assertEqual(original["Gradations"][2], identity)

    def test_curve_validation(self):
        for row in [
            ["rgb", "4:0", "255:255"],
            ["red", "0:0", "255:300"],
            ["cyan", "0:0", "255:255"],
            ["rgb", "0:0", "128:8", "128:42", "255:255"],
            ["rgb", "0:0", "invalid", "255:255"],
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                api["curve_args"]([row])

    def test_checkerboard_is_a_plist_boolean(self):
        data = plistlib.loads(self.content)
        data["ImageSettings"][1]["ImageCorrection"].update(
            GreenGreen=False, ApplyCNFilter=False
        )
        self.file.write_bytes(plistlib.dumps(data))
        result = api["variant"](self.raw, self.root, {"remove_checkerboard": 1})
        _, settings = api["load_settings"](Path(result["raw"]))
        self.assertIs(settings["GreenGreen"], True)
        self.assertIs(settings["ApplyCNFilter"], True)

    def test_unknown_and_malformed_sidecars_report_cli_error(self):
        import json
        import subprocess

        cli = Path(__file__).with_name("phocus")
        for payload in (
            b"<?xml version='1.0'?><plist><dict>",
            plistlib.dumps({"ImageSettings": [], "CurrentIx": 0}),
        ):
            self.file.write_bytes(payload)
            result = subprocess.run(
                [str(cli), "inspect", str(self.raw)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("error", json.loads(result.stderr))

    def test_same_output_and_watch_rejected_before_staging(self):
        with self.assertRaises(ValueError):
            api["render"](self.raw, self.root, self.root, self.root, {}, 1)
        self.assertFalse(list(self.root.glob("phjob*")))


if __name__ == "__main__":
    unittest.main()
