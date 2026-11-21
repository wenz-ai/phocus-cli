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


if __name__ == "__main__":
    unittest.main()
