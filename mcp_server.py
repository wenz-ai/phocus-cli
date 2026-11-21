"""stdio bridge for the phocus CLI. Launch with a fixed library, spool and output root."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

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
    if not path.is_relative_to(library) or path.suffix.lower() != ".3fr":
        raise ValueError("请指定 library 内的 .3FR")
    sidecar = Path(str(path) + ".phos")
    if sidecar.is_symlink() and not sidecar.resolve().is_relative_to(library):
        raise ValueError("sidecar 超出 library 范围")
    return path


def call(*args):
    proc = subprocess.run(
        [str(cli), *map(str, args)], text=True, check=False, capture_output=True
    )
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def settings(changes):
    return ["--set", *(f"{k}={v}" for k, v in changes.items())] if changes else []


@server.tool()
def capabilities() -> dict:
    """List edit keys, numeric ranges and native sidecar fields."""
    return call("capabilities")


@server.tool()
def inspect_photo(photo: str) -> dict:
    """Read saved adjustments and version names from a RAW's own sidecar, without opening Phocus."""
    return call("inspect", source_path(photo))


@server.tool()
def make_variant(photo: str, changes: dict[str, float]) -> dict:
    """Write a new editable RAW + sidecar in the output root, offline."""
    return call("variant", source_path(photo), "--out", output, *settings(changes))


@server.tool()
def render_photos(photos: list[str], changes: dict[str, float]) -> list[dict]:
    """Apply a recipe and render in background Phocus. Return file paths and values only."""
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
        *settings(changes),
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
