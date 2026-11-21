"""stdio bridge for the phocus CLI. Launch with a fixed library, spool and output root."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from mcp.server.fastmcp import FastMCP, Image

parser = argparse.ArgumentParser(description=__doc__)
for name in ("library", "watch", "spool", "out"):
    parser.add_argument("--" + name, required=True, type=Path)
config = parser.parse_args()
library, watch, spool, output = (
    p.expanduser().resolve()
    for p in (config.library, config.watch, config.spool, config.out)
)
cli = Path(__file__).resolve().with_name("phocus")
server = FastMCP("Phocus Local")


def source_path(name: str) -> Path:
    path = (library / name).resolve(strict=True)
    allowed = next(
        (base for base in (library, output) if path.is_relative_to(base)), None
    )
    if allowed is None or path.suffix.lower() != ".3fr":
        raise ValueError("请指定 library 内的 .3FR")
    sidecar = Path(str(path) + ".phos")
    if sidecar.is_symlink() and not sidecar.resolve().is_relative_to(allowed):
        raise ValueError("sidecar 超出 library 范围")
    return path


def call(*args):
    proc = subprocess.run(
        [sys.executable, str(cli), *map(str, args)],
        text=True,
        check=False,
        capture_output=True,
    )
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


class Delivery(BaseModel):
    """Optional SDR file exported from the Phocus master. Dimensions never upscale."""

    model_config = ConfigDict(extra="forbid")
    format: Literal["jpeg", "png"] = "jpeg"
    long_edge: int | None = Field(default=None, ge=1, le=65535)
    jpeg_quality: int | None = Field(default=None, ge=1, le=100)
    srgb: bool = False
    watermark_exif: bool = False
    watermark_text: str | None = None
    watermark_logo: str | None = None
    watermark_corner: (
        Literal["top-left", "top-right", "bottom-left", "bottom-right"] | None
    ) = None
    watermark_width: float | None = None
    watermark_opacity: int | None = None


def library_logo(name):
    asset = (library / name).resolve(strict=True)
    if not asset.is_relative_to(library) or asset.suffix.lower() != ".png":
        raise ValueError("请选择 library 内的 PNG")
    return asset


def delivery_args(options):
    if options is None:
        return []
    values = options.model_dump(exclude_none=True)
    args = ["--export-format", values.pop("format")]
    if values.pop("watermark_exif"):
        args.append("--watermark-exif")
    if values.pop("srgb"):
        args.append("--srgb")
    if "watermark_logo" in values:
        values["watermark_logo"] = library_logo(values["watermark_logo"])
    for key, v in values.items():
        args.extend(["--" + key.replace("_", "-"), v])
    return args


Curves = dict[str, list[tuple[StrictInt, StrictInt]]]


def settings(changes, crop=None, rotate=None, curves=None):
    args = ["--set", *(f"{k}={v}" for k, v in changes.items())] if changes else []
    if crop is not None:
        if len(crop) != 4:
            raise ValueError("crop 需要四个边界")
        args.extend(["--crop", *crop])
    if rotate is not None:
        args.extend(["--rotate", rotate])
    for channel, points in (curves or {}).items():
        args.extend(["--curve", channel, *(f"{x}:{y}" for x, y in points)])
    return args


@server.tool()
def capabilities() -> dict:
    """List edit keys, numeric ranges and native sidecar fields."""
    return call("capabilities")


@server.tool()
def inspect_photo(photo: str) -> dict:
    """Read saved adjustments and version names from a RAW's own sidecar, without opening Phocus."""
    return call("inspect", source_path(photo))


@server.tool()
def make_variant(
    photo: str,
    changes: dict[str, float] | None = None,
    crop: list[float] | None = None,
    rotate: int | None = None,
    curves: Curves | None = None,
) -> dict:
    """Create an editable RAW copy offline. Crop is normalized [left, top, right, bottom]; rotate is degrees CCW."""
    return call(
        "variant",
        source_path(photo),
        "--out",
        output,
        *settings(changes, crop, rotate, curves),
    )


@server.tool()
def render_photos(
    photos: list[str],
    changes: dict[str, float] | None = None,
    crop: list[float] | None = None,
    rotate: int | None = None,
    curves: Curves | None = None,
    delivery: Delivery | None = None,
) -> list[dict]:
    """Render RAW masters with optional SDR delivery copies. Curves map rgb/red/green/blue to [x,y] points (0..255); crop is normalized LTRB and rotate is degrees CCW."""
    if not photos:
        raise ValueError("photos 至少需要一张照片")
    return call(
        "render",
        *(source_path(photo) for photo in photos),
        "--watch",
        watch,
        "--spool",
        spool,
        "--out",
        output,
        *settings(changes, crop, rotate, curves),
        *delivery_args(delivery),
    )


@server.tool()
def export_photos(files: list[str], delivery: Delivery) -> list[dict]:
    """Batch export finished SDR JPEG/PNG files from library or output, with optional sizing, sRGB and watermark."""
    if not files:
        raise ValueError("请选择至少一张已渲染图片")
    paths = []
    for file in files:
        path = (library / file).resolve(strict=True)
        if not any(
            path.is_relative_to(root) for root in (library, output)
        ) or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError("请选择 library 或输出目录内的 JPEG/PNG")
        paths.append(path)
    return call("export", *paths, "--out", output, *delivery_args(delivery))


@server.tool()
def denoise_raw(photo: str, mode: str) -> dict:
    """Submit the native HNNR mode (purity/detail). Uses Phocus desktop UI; requires its viewed queue empty and auto-export off."""
    return call(
        "hnnr", source_path(photo), "--mode", mode, "--watch", watch, "--out", output
    )


@server.tool()
def watermark_result(
    file: str,
    text: str | None = None,
    logo: str | None = None,
    corner: str = "bottom-right",
    width_pct: float = 18,
    opacity: int = 65,
    format: str = "jpeg",
    exif: bool = False,
) -> dict:
    """Create a marked copy of an SDR output. Supply either text or a PNG logo from the library."""
    path = (output / file).resolve(strict=True)
    if not path.is_relative_to(output):
        raise ValueError("请选择输出目录中的成片")
    if sum((text is not None, logo is not None, exif)) != 1:
        raise ValueError("请选择文字、拍摄参数或 logo 其中一种")
    if logo is not None:
        asset = library_logo(logo)
        mark = ["--logo", asset]
    elif exif:
        mark = ["--exif"]
    else:
        mark = ["--text", text]
    return call(
        "watermark",
        path,
        "--out",
        output,
        *mark,
        "--corner",
        corner,
        "--width-pct",
        width_pct,
        "--opacity",
        opacity,
        "--format",
        format,
    )


@server.tool()
def preview_result(file: str, crop: list[int] | None = None) -> Image:
    """Return a 1280px overview, or a native-resolution crop [x, y, width, height] from the top left."""
    path = (output / file).resolve(strict=True)
    if not path.is_relative_to(output) or path.suffix.lower() not in {
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".png",
    }:
        raise ValueError("请指定输出目录中的成片")
    transform = ["-Z", "1280"]
    if crop is not None:
        if len(crop) != 4:
            raise ValueError("crop 应为 [x, y, width, height]")
        x, y, width, height = crop
        if min(x, y) < 0 or not (1 <= width <= 1280 and 1 <= height <= 1280):
            raise ValueError("起点应为非负整数，局部预览每边为 1–1280 像素")
        size = subprocess.check_output(
            ["/usr/bin/sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            text=True,
        )
        dimensions = dict(
            line.strip().split(": ", 1) for line in size.splitlines() if ": " in line
        )
        if x + width > int(dimensions["pixelWidth"]) or y + height > int(
            dimensions["pixelHeight"]
        ):
            raise ValueError("局部预览超出图像边界")
        transform = [
            "--cropToHeightWidth",
            str(height),
            str(width),
            "--cropOffset",
            str(y),
            str(x),
        ]
    with tempfile.TemporaryDirectory() as folder:
        dest = Path(folder) / "preview.jpg"
        proc = subprocess.run(
            [
                "/usr/bin/sips",
                *transform,
                "-s",
                "format",
                "jpeg",
                str(path),
                "--out",
                str(dest),
            ],
            text=True,
            check=False,
            capture_output=True,
        )
        if proc.returncode:
            raise ValueError(proc.stderr)
        return Image(data=dest.read_bytes(), format="jpeg")


if __name__ == "__main__":
    server.run(transport="stdio")
