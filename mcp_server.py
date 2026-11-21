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
def preview_result(file: str) -> Image:
    """Return a 1280px JPEG for visual comparison when needed. Accepts a rendered output's path."""
    path = (output / file).resolve(strict=True)
    if not path.is_relative_to(output) or path.suffix.lower() not in {
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".png",
    }:
        raise ValueError("请指定输出目录中的成片")
    with tempfile.TemporaryDirectory() as folder:
        dest = Path(folder) / "preview.jpg"
        proc = subprocess.run(
            [
                "/usr/bin/sips",
                "-Z",
                "1280",
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
