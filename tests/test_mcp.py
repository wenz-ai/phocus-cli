"""Run with the MCP SDK and Pillow installed. No desktop app or RAW is required."""

import io
import json
import plistlib
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def connected(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        dirs = {k: self.base / k for k in ("library", "watch", "spool", "out")}
        for d in dirs.values():
            d.mkdir()
        self.library, self.out = dirs["library"], dirs["out"]
        raw = self.library / "test.3FR"
        raw.write_bytes(b"synthetic")
        Path(str(raw) + ".phos").write_bytes(
            plistlib.dumps(
                {
                    "Version": 31,
                    "CurrentIx": 0,
                    "ImageSettings": [
                        {
                            "Name": "base",
                            "ImageCorrection": {
                                "streamableVersion": 11,
                                "EV": 1.0,
                                "ApplyEV": True,
                            },
                        }
                    ],
                }
            )
        )
        opts = StdioServerParameters(
            command=sys.executable,
            args=[
                str(ROOT / "mcp_server.py"),
                *(
                    item
                    for key, value in dirs.items()
                    for item in ("--" + key, str(value))
                ),
            ],
        )
        async with stdio_client(opts) as (rx, tx), ClientSession(rx, tx) as client:
            await client.initialize()
            yield client

    async def test_contract_offline_edits_and_errors(self):
        async with self.connected() as client:
            tools = await client.list_tools()
            self.assertEqual(
                {t.name for t in tools.tools},
                {
                    "capabilities",
                    "denoise_raw",
                    "watermark_result",
                    "export_photos",
                    "list_official_frames",
                    "export_official_frames",
                    "inspect_photo",
                    "make_variant",
                    "render_photos",
                    "preview_result",
                },
            )
            r = await client.call_tool("capabilities", {})
            self.assertFalse(r.isError)
            self.assertEqual(
                json.loads(r.content[0].text)["color_noise_radius"]["range"], [0, 50]
            )
            r = await client.call_tool(
                "make_variant", {"photo": "test.3FR", "changes": {"exposure": 1}}
            )
            self.assertFalse(r.isError)
            p = Path(json.loads(r.content[0].text)["sidecar"])
            self.assertEqual(
                plistlib.loads(p.read_bytes())["ImageSettings"][0]["ImageCorrection"][
                    "EV"
                ],
                2,
            )
            r = await client.call_tool("inspect_photo", {"photo": "test.3FR"})
            self.assertEqual(json.loads(r.content[0].text)["values"]["exposure"], 0)
            self.assertTrue(
                (
                    await client.call_tool(
                        "render_photos", {"photos": [], "changes": {}}
                    )
                ).isError
            )
            outsider = self.base / "outside.3FR"
            outsider.write_bytes(b"x")
            (self.library / "link.3FR").symlink_to(outsider)
            self.assertTrue(
                (await client.call_tool("inspect_photo", {"photo": "link.3FR"})).isError
            )

    async def test_watermark_uses_output_root_and_preserves_unmarked_pixels(self):
        async with self.connected() as client:
            image = Image.new("RGB", (200, 100), (35, 45, 55))
            image.save(self.out / "photo.png")
            logo = Image.new("RGBA", (16, 8), (255, 0, 0, 255))
            logo.putpixel((0, 0), (0, 0, 0, 0))
            logo.save(self.library / "logo.png")
            req = {
                "file": "photo.png",
                "logo": "logo.png",
                "width_pct": 8,
                "opacity": 100,
                "format": "png",
            }
            result = await client.call_tool("watermark_result", req)
            self.assertFalse(result.isError, result.content)
            payload = json.loads(result.content[0].text)
            x, y, w, h = payload["mark_box"]
            from PIL import ImageChops

            with Image.open(payload["output"]) as marked:
                self.assertEqual(marked.size, image.size)
                self.assertEqual(marked.getpixel((x, y)), image.getpixel((x, y)))
                self.assertEqual(marked.getpixel((x + 3, y + 2)), (255, 0, 0))
                self.assertEqual(
                    ImageChops.difference(marked, image).getbbox(), (x, y, x + w, y + h)
                )
            bad = await client.call_tool(
                "watermark_result", {**req, "file": str(self.library / "logo.png")}
            )
            self.assertTrue(bad.isError)
            bad = await client.call_tool(
                "denoise_raw", {"photo": "test.3FR", "mode": "unknown"}
            )
            self.assertTrue(bad.isError)

    async def test_batch_delivery_resize_color_and_permissions(self):
        async with self.connected() as client:
            from PIL import ImageCms

            for name, size in [("large", (160, 320)), ("small", (20, 10))]:
                im = Image.new("RGB", size, "green")
                exif = Image.Exif()
                exif[272] = "Test Camera"
                im.save(self.library / (name + ".jpg"), exif=exif)
            request = {
                "files": ["large.jpg", "small.jpg"],
                "delivery": {
                    "long_edge": 80,
                    "format": "jpeg",
                    "jpeg_quality": 85,
                    "srgb": True,
                    "watermark_exif": True,
                },
            }
            res = await client.call_tool("export_photos", request)
            self.assertFalse(res.isError, res.content)
            rows = [json.loads(c.text) for c in res.content]
            if isinstance(rows[0], list):
                rows = rows[0]
            self.assertEqual([r["pixels"] for r in rows], [[40, 80], [20, 10]])
            for row in rows:
                self.assertEqual(row["caption"], "Test Camera")
                with Image.open(row["output"]) as result:
                    self.assertNotIn(272, result.getexif())
                    profile = ImageCms.ImageCmsProfile(
                        io.BytesIO(result.info["icc_profile"])
                    )
                    self.assertIn(
                        "srgb", ImageCms.getProfileDescription(profile).lower()
                    )
            bad = await client.call_tool(
                "export_photos",
                {**request, "delivery": {"format": "png", "jpeg_quality": 80}},
            )
            self.assertTrue(bad.isError)
            bad = await client.call_tool(
                "export_photos",
                {
                    **request,
                    "delivery": {"watermark_exif": True, "watermark_text": "also"},
                },
            )
            self.assertTrue(bad.isError)
            outsider = self.base / "outside.jpg"
            Image.new("RGB", (5, 5)).save(outsider)
            (self.library / "escape.jpg").symlink_to(outsider)
            res = await client.call_tool(
                "export_photos", {"files": ["escape.jpg"], "delivery": {}}
            )
            self.assertTrue(res.isError)

    async def test_overview_and_detail_preview(self):
        async with self.connected() as client:
            img = Image.new("RGB", (1600, 1200), (10, 190, 10))
            img.paste((230, 20, 20), (640, 280, 800, 400))
            img.save(self.out / "chart.png")

            async def preview(**options):
                response = await client.call_tool(
                    "preview_result", {"file": "chart.png", **options}
                )
                self.assertFalse(response.isError, response.content)
                import base64

                return Image.open(
                    io.BytesIO(base64.b64decode(response.content[0].data))
                )

            overview = await preview()
            self.assertEqual(overview.size, (1280, 960))
            detail = await preview(crop=[640, 280, 160, 120])
            self.assertEqual(detail.size, (160, 120))
            red, green, blue = detail.getpixel((80, 60))
            self.assertGreater(red, 200)
            self.assertLess(green, 40)
            for rect in [
                [1, 2, 3],
                [-1, 0, 10, 10],
                [1590, 0, 11, 10],
                [0, 0, 1300, 20],
            ]:
                self.assertTrue(
                    (
                        await client.call_tool(
                            "preview_result", {"file": "chart.png", "crop": rect}
                        )
                    ).isError
                )


if __name__ == "__main__":
    unittest.main()
