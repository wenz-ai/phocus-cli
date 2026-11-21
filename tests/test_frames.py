import tempfile
import unittest
from pathlib import Path
from PIL import Image
from official_frames import STYLES, STYLE_MARK, prepare, select_styles


class FrameTests(unittest.TestCase):
    def test_picker_order_and_eligibility(self):
        self.assertEqual(list(STYLES.values()), [12, 6, 7, 1, 2, 3, 4, 8, 9])
        self.assertEqual(len(select_styles(["all"], False)), 7)
        self.assertEqual(len(select_styles(["all"], True)), 9)
        for names in (
            [],
            ["all", "hasselblad-1"],
            ["explorer-1"],
            ["invalid"],
            ["hasselblad-1"] * 2,
        ):
            with self.subTest(names=names), self.assertRaises(ValueError):
                select_styles(names, False)

    def test_metadata_resize_and_reject_second_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.jpg"
            tags = Image.Exif()
            tags[271] = "Hasselblad"
            tags[272] = "X2D 100C"
            im = Image.new("RGB", (100, 200), "olive")
            im.save(path, exif=tags)
            result, names, meta, icc = prepare(path, ["all"], 80)
            self.assertEqual(result.size, (40, 80))
            self.assertEqual(len(names), 7)
            self.assertEqual(meta[0], "Hasselblad X2D 100C")
            self.assertTrue(icc)
            tags[305] = STYLE_MARK + "hasselblad-1"
            im.save(path, exif=tags)
            with self.assertRaisesRegex(ValueError, "已有画框"):
                prepare(path, ["all"], 80)
            im.save(path)
            with self.assertRaisesRegex(ValueError, "机型"):
                prepare(path, ["all"], 80)
