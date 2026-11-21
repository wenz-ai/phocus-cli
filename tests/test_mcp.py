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
                    "sample_color",
                    "analyze_exposure",
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
            schemas = {t.name: t.inputSchema["properties"] for t in tools.tools}
            variant_fields = dict(schemas["make_variant"])
            render_fields = dict(schemas["render_photos"])
            del variant_fields["photo"], render_fields["photos"], render_fields["delivery"]
            self.assertEqual(variant_fields, render_fields)
            self.assertTrue(all(t.title for t in tools.tools))
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

    async def test_oriented_exposure_endpoints_and_bounds(self):
        async with self.connected() as client:
            img = Image.new("RGB", (4, 2), (245, 10, 10))
            img.paste((255, 0, 3), (0, 0, 1, 2))
            exif = Image.Exif()
            exif[274] = 6
            img.save(self.out / "ramp.png", exif=exif)
            req = {"file": str(self.out / "ramp.png")}

            async def stats(**kwargs):
                result = await client.call_tool("analyze_exposure", {**req, **kwargs})
                self.assertFalse(result.isError, result.content)
                return json.loads(result.content[0].text)

            full = await stats()
            self.assertEqual(full["image_size"], [2, 4])
            self.assertEqual(full["channels"]["red"]["at_255_pct"], 25)
            part = await stats(region=[0, 0, 1, 0.25])
            self.assertEqual(part["pixels"], 2)
            self.assertEqual(part["channels"]["green"]["at_0_pct"], 100)
            self.assertEqual(part["channels"]["blue"]["at_0"], 0)
            for bounds in ([0, 0, 0, 1], [-1, 0, 1, 1]):
                self.assertTrue(
                    (
                        await client.call_tool(
                            "analyze_exposure", {**req, "region": bounds}
                        )
                    ).isError
                )
            outside = self.base / "outside.png"
            img.save(outside)
            (self.library / "linked.png").symlink_to(outside)
            self.assertTrue(
                (
                    await client.call_tool("analyze_exposure", {"file": "linked.png"})
                ).isError
            )

    async def test_color_sampling_and_offline_recipe(self):
        async with self.connected() as client:
            img = Image.new("RGB", (24, 16), "yellow")
            img.paste((220, 220, 220), (12, 0, 24, 16))
            img.save(self.library / "colors.png")
            for x, expected in ((0.0, 60.0), (1.0, None)):
                reply = await client.call_tool(
                    "sample_color",
                    {"file": "colors.png", "x": x, "y": 0.5, "radius": 2},
                )
                self.assertFalse(reply.isError)
                self.assertEqual(
                    json.loads(reply.content[0].text)["estimated_hue"], expected
                )
            path = self.library / "test.3FR.phos"
            data = plistlib.loads(path.read_bytes())
            native = data["ImageSettings"][0]["ImageCorrection"]
            for suffix in ("SrcH", "SrcL", "SrcS", "Angle", "DstH", "DstL", "DstS"):
                native["Selective" + suffix] = []
            for chan in ("", "Red", "Green", "Blue"):
                native["Gamma" + chan] = 2.0
            native.update(Shadow=[0] * 4, Highlight=[16320] * 4)
            path.write_bytes(plistlib.dumps(data))
            reply = await client.call_tool(
                "make_variant",
                {
                    "photo": "test.3FR",
                    "color_bands": [{"hue": "yellow", "shift": 8}],
                    "levels": {"rgb": {"black": 12, "mid": 1.15, "white": 247}},
                },
            )
            self.assertFalse(reply.isError, reply.content)
            variant = json.loads(reply.content[0].text)
            reply = await client.call_tool("inspect_photo", {"photo": variant["raw"]})
            self.assertFalse(reply.isError)
            info = json.loads(reply.content[0].text)
            self.assertEqual(info["color_bands"][0]["shift"], 8)
            self.assertEqual(info["levels"]["blue"], [12, 1.15, 247])

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
            after = Image.new("RGB", img.size, (0, 40, 250))
            after.save(self.out / "after.png")
            pair = await preview(compare_with="after.png", crop=[640, 280, 160, 120])
            self.assertEqual(pair.size, (322, 120))
            self.assertEqual(pair.getpixel((80, 60)), (230, 20, 20))
            self.assertEqual(pair.getpixel((242, 60)), (0, 40, 250))
            bad = await client.call_tool("preview_result", {"file": "chart.png", "compare_with": str(self.library / "test.3FR")})
            self.assertTrue(bad.isError)
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
