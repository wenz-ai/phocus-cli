"""Apply a visible mark to a separate SDR export; the RAW and its settings stay intact."""

import math
import os
import tempfile
import uuid
from pathlib import Path


def stamp(
    source,
    out,
    *,
    text=None,
    logo=None,
    corner="bottom-right",
    width_pct=18,
    opacity=65,
    fmt="jpeg",
):
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:
        raise ValueError(
            "水印功能需要 Pillow，请用安装了 Pillow 的 Python 运行"
        ) from exc

    if (text is None) == (logo is None):
        raise ValueError("请选择文字或透明 PNG logo")
    if text is not None and (
        not text.strip() or len(text) > 240 or not text.isprintable()
    ):
        raise ValueError("请输入 1–240 个可打印字符")
    if (
        not (1 <= width_pct <= 60 and 1 <= opacity <= 100)
        or corner not in {"top-left", "top-right", "bottom-left", "bottom-right"}
        or fmt not in {"jpeg", "png"}
    ):
        raise ValueError("水印位置、尺寸、透明度或格式无效")
    Image.MAX_IMAGE_PIXELS = 155_000_000
    with Image.open(source) as original:
        if (
            original.format not in {"JPEG", "PNG"}
            or original.mode not in {"RGB", "L", "RGBA"}
            or getattr(original, "n_frames", 1) != 1
        ):
            raise ValueError("水印当前支持单张 8 位 SDR JPEG/PNG")
        if original.format == "PNG":
            with source.open("rb") as stream:
                header = stream.read(25)
            if len(header) < 25 or header[24] != 8:
                raise ValueError("PNG 水印仅支持每通道 8 位图像")
        if original.mode == "L" and original.info.get("icc_profile"):
            raise ValueError("当前未验证带灰度 ICC 的水印输入")
        if (
            any(k in original.info for k in ("mp", "cicp", "cICP"))
            or b"hdrgm:" in str(original.info.get("xmp", "")).encode()
        ):
            raise ValueError("暂不支持增益图或带独立传递函数的图像")
        if fmt == "jpeg" and original.mode == "RGBA":
            raise ValueError("带透明通道的输入请选择 PNG 输出")
        canvas = ImageOps.exif_transpose(original).copy()
        if canvas.mode == "L":
            canvas = canvas.convert("RGB")
        profile = original.info.get("icc_profile")
    w, h = canvas.size
    margin = max(1, round(min(w, h) * 0.022))
    max_w = min(w - 2 * margin, max(1, round(w * width_pct / 100)))
    max_h = min(h - 2 * margin, max(1, h // 3))
    if min(max_w, max_h) < 1:
        raise ValueError("输入图像太小")
    if logo is not None:
        with Image.open(logo) as source_logo:
            if source_logo.format != "PNG" or getattr(source_logo, "n_frames", 1) != 1:
                raise ValueError("logo 必须为单张 PNG")
            mark = source_logo.convert("RGBA")
    else:
        font_path = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
        if not font_path.exists():
            font_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
        font = ImageFont.truetype(str(font_path), 96)
        x0, y0, x1, y1 = font.getbbox(text, stroke_width=2)
        mark = Image.new("RGBA", (max(1, x1 - x0), max(1, y1 - y0)))
        ImageDraw.Draw(mark).text(
            (-x0, -y0),
            text,
            font=font,
            fill="white",
            stroke_width=2,
            stroke_fill="#202020",
        )
    ratio = min(max_w / mark.width, max_h / mark.height)
    mark = mark.resize(
        (
            max(1, math.floor(mark.width * ratio)),
            max(1, math.floor(mark.height * ratio)),
        ),
        Image.Resampling.LANCZOS,
    )
    x = margin if corner.endswith("left") else w - margin - mark.width
    y = margin if corner.startswith("top") else h - margin - mark.height
    mark.putalpha(mark.getchannel("A").point(lambda a: round(a * opacity / 100)))
    if canvas.mode == "RGBA":
        canvas.alpha_composite(mark, dest=(x, y))
    else:
        canvas.paste(mark, (x, y), mark.getchannel("A"))
    out.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if fmt == "jpeg" else "png"
    target = out / (source.stem + "-watermark-" + uuid.uuid4().hex[:12] + "." + ext)
    # Save orientation-normalized pixels and the source color profile. Omit capture metadata.
    canvas.info.clear()
    opts = {"icc_profile": profile} if profile is not None else {}
    if fmt == "jpeg":
        opts.update(quality=95, subsampling=0)
    with tempfile.TemporaryDirectory(dir=out) as folder:
        staged = Path(folder) / ("image." + ext)
        canvas.save(staged, **opts)
        os.link(staged, target)
    return {
        "output": str(target),
        "pixels": [w, h],
        "mark_box": [x, y, mark.width, mark.height],
        "engine": "Pillow",
    }
