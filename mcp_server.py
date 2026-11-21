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


class Levels(BaseModel):
    """Input black and white in 0..255, midpoint 1 is neutral."""

    model_config = ConfigDict(extra="forbid")
    black: StrictInt = Field(default=0, ge=0, le=254)
    mid: float = Field(default=1, ge=0.1, le=4)
    white: StrictInt = Field(default=255, ge=1, le=255)


class ColorBand(BaseModel):
    """One native selective color point; hue may be degrees or a color name."""

    model_config = ConfigDict(extra="forbid")
    hue: (
        float
        | Literal[
            "red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta"
        ]
    )
    width: float = Field(default=30, ge=1, le=90)
    shift: float = Field(default=0, ge=-45, le=45)
    saturation: float = Field(default=1, ge=0.3, le=1.7)
    lightness: float = Field(default=0, ge=-50, le=50)


class LinearMask(BaseModel):
    """Exposure reaches ev at full and zero at zero. Coordinates are normalized to the original photo."""

    model_config = ConfigDict(extra="forbid")
    name: str
    full: tuple[float, float]
    zero: tuple[float, float]
    ev: float = Field(ge=-4, le=4)


class RadialMask(BaseModel):
    """Ellipse in original image coordinates. Radii are fractions of image width and height."""
    model_config = ConfigDict(extra="forbid")
    name: str
    center: tuple[float, float]
    radii: tuple[float, float]
    angle: float = Field(default=0, ge=-180, le=180)
    feather: float = Field(default=0.1, ge=0, le=1)
    side: Literal["inside", "outside"] = "inside"
    ev: float = Field(ge=-4, le=4)


def adjustment_args(
    *,
    changes,
    crop,
    rotate,
    curves,
    straighten,
    levels,
    color_bands,
    clear_color_bands,
    linear_masks,
    radial_masks,
    layer_adjustments,
):
    args = ["--set", *(f"{k}={v}" for k, v in changes.items())] if changes else []
    if crop is not None:
        if len(crop) != 4:
            raise ValueError("crop 需要四个边界")
        args.extend(["--crop", *crop])
    if straighten is not None:
        args.extend(["--straighten", straighten])
    if rotate is not None:
        args.extend(["--rotate", rotate])
    for channel, points in (curves or {}).items():
        args.extend(["--curve", channel, *(f"{x}:{y}" for x, y in points)])
    for channel, entry in (levels or {}).items():
        args.extend(["--levels", channel, entry.black, entry.mid, entry.white])
    for band in color_bands or []:
        args.extend(
            [
                "--color-band",
                band.hue,
                band.width,
                band.shift,
                band.saturation,
                band.lightness,
            ]
        )
    for mask in linear_masks or []:
        args.extend(["--linear-mask", mask.name, *mask.full, *mask.zero, mask.ev])
    for mask in radial_masks or []:
        args.extend(["--radial-mask", mask.name, *mask.center, *mask.radii, mask.angle, mask.feather, mask.side, mask.ev])
    for name, edits in (layer_adjustments or {}).items():
        for field, value in edits.items():
            args.extend(["--layer-adjust", name, field, value])
    if clear_color_bands:
        args.append("--clear-color-bands")
    return args


@server.tool(title="检查原片 · 可调参数")
def capabilities() -> dict:
    """List edit keys, numeric ranges and native sidecar fields."""
    return call("capabilities")


def sdr_path(file: str) -> Path:
    path = (library / file).resolve(strict=True)
    if not any(
        path.is_relative_to(root) for root in (library, output)
    ) or path.suffix.lower() not in {".jpeg", ".jpg", ".png"}:
        raise ValueError("请选择 library 或输出目录中的 SDR 预览")
    return path


@server.tool(title="检查成片 · 曝光端点")
def analyze_exposure(
    file: str, region: tuple[float, float, float, float] | None = None
) -> dict:
    """Count pixels at 0 and 255 per sRGB channel in a rendered SDR JPEG/PNG. Optional normalized oriented LTRB region. Measures the rendition, not RAW sensor clipping."""
    args = ["--region", *region] if region is not None else []
    return call("exposure-stats", sdr_path(file), *args)


@server.tool(title="检查成片 · 颜色取样")
def sample_color(file: str, x: float, y: float, radius: int = 4) -> dict:
    """Sample an sRGB preview at normalized (x,y) from top left. estimated_hue is a starting point for a color band; neutral patches return null."""
    return call("sample", sdr_path(file), "--at", x, y, "--radius", radius)


@server.tool(title="检查原片 · 已存调整")
def inspect_photo(photo: str) -> dict:
    """Read saved adjustments and version names from a RAW's own sidecar, without opening Phocus."""
    return call("inspect", source_path(photo))


@server.tool(title="处理 RAW · 创建可编辑副本")
def make_variant(
    photo: str,
    changes: dict[str, float] | None = None,
    crop: list[float] | None = None,
    rotate: int | None = None,
    curves: Curves | None = None,
    straighten: float | None = None,
    levels: dict[str, Levels] | None = None,
    color_bands: list[ColorBand] | None = None,
    clear_color_bands: bool = False,
    linear_masks: list[LinearMask] | None = None,
    radial_masks: list[RadialMask] | None = None,
    layer_adjustments: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Create an editable RAW copy offline. Crop is normalized [left, top, right, bottom]; rotate is degrees CCW."""
    return call(
        "variant",
        source_path(photo),
        "--out",
        output,
        *adjustment_args(
            changes=changes,
            crop=crop,
            rotate=rotate,
            curves=curves,
            straighten=straighten,
            levels=levels,
            color_bands=color_bands,
            clear_color_bands=clear_color_bands,
            linear_masks=linear_masks,
            radial_masks=radial_masks,
            layer_adjustments=layer_adjustments,
        ),
    )


@server.tool(title="处理 RAW · 渲染母版")
def render_photos(
    photos: list[str],
    changes: dict[str, float] | None = None,
    crop: list[float] | None = None,
    rotate: int | None = None,
    curves: Curves | None = None,
    straighten: float | None = None,
    levels: dict[str, Levels] | None = None,
    color_bands: list[ColorBand] | None = None,
    clear_color_bands: bool = False,
    linear_masks: list[LinearMask] | None = None,
    radial_masks: list[RadialMask] | None = None,
    layer_adjustments: dict[str, dict[str, float]] | None = None,
    delivery: Delivery | None = None,
) -> list[dict]:
    """Render RAW masters with optional SDR delivery copies. Curves map rgb/red/green/blue/luma to [x,y] points (0..255); crop is normalized LTRB and rotate is degrees CCW."""
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
        *adjustment_args(
            changes=changes,
            crop=crop,
            rotate=rotate,
            curves=curves,
            straighten=straighten,
            levels=levels,
            color_bands=color_bands,
            clear_color_bands=clear_color_bands,
            linear_masks=linear_masks,
            radial_masks=radial_masks,
            layer_adjustments=layer_adjustments,
        ),
        *delivery_args(delivery),
    )


@server.tool(title="交付 · 批量导出")
def export_photos(files: list[str], delivery: Delivery) -> list[dict]:
    """Batch export finished SDR JPEG/PNG files from library or output, with optional sizing, sRGB and watermark."""
    if not files:
        raise ValueError("请选择至少一张已渲染图片")
    paths = [sdr_path(file) for file in files]
    return call("export", *paths, "--out", output, *delivery_args(delivery))


@server.tool(title="交付 · 查看画框款式")
def list_official_frames() -> dict:
    """List all 7 Hasselblad and 2 Earth Explorer styles in the Windows Phocus 4.2 picker."""
    return call("frames", "list")


@server.tool(title="交付 · 导出官方画框")
def export_official_frames(
    file: str, styles: list[str], long_edge: int | None = None, quality: int = 95
) -> dict:
    """Render genuine Windows Phocus frames on Hasselblad RAW (first render the master) or an unframed SDR JPEG. Use ["all"] for all eligible styles. Long edge limits photo content before framing."""
    path = (library / file).resolve(strict=True)
    if path.suffix.lower() == ".3fr":
        path = source_path(file)
    if not any(
        path.is_relative_to(base) for base in (library, output)
    ) or path.suffix.lower() not in {".jpg", ".jpeg", ".3fr"}:
        raise ValueError("请选择 library 或输出目录内的哈苏 RAW 或未加框的 JPEG 母版")
    if not styles:
        raise ValueError("请选择款式或 all")
    options = ["--long-edge", long_edge] if long_edge is not None else []
    return call(
        "frames",
        "export",
        path,
        "--styles",
        *styles,
        "--watch",
        watch,
        "--spool",
        spool,
        "--out",
        output,
        "--quality",
        quality,
        *options,
    )


@server.tool(title="处理 RAW · HNNR 降噪")
def denoise_raw(photo: str, mode: str) -> dict:
    """Submit the native HNNR mode (purity/detail). Uses Phocus desktop UI; requires its viewed queue empty and auto-export off."""
    return call(
        "hnnr", source_path(photo), "--mode", mode, "--watch", watch, "--out", output
    )


@server.tool(title="交付 · 单张加水印")
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


@server.tool(title="检查成片 · 整图或局部预览")
def preview_result(file: str, crop: list[int] | None = None, compare_with: str | None = None) -> Image:
    """Return a 1280px overview, or a native-resolution crop [x, y, width, height] from the top left. Pass compare_with for an SDR comparison: file on the left, compare_with on the right."""
    path = (output / file).resolve(strict=True)
    if not path.is_relative_to(output) or path.suffix.lower() not in {
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".png",
    }:
        raise ValueError("请指定输出目录中的成片")
    if compare_with is not None:
        import io
        from tone_controls import compare_previews

        after = (output / compare_with).resolve(strict=True)
        if not after.is_relative_to(output):
            raise ValueError("请选择输出目录中的成片")
        canvas = compare_previews(path, after, crop)
        encoded = io.BytesIO()
        canvas.save(encoded, format="PNG")
        return Image(data=encoded.getvalue(), format="png")
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
