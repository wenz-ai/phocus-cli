"""Apply a visible mark to a separate SDR export; the RAW and its settings stay intact."""

import io
import math
import os
import tempfile
import uuid
from pathlib import Path


def validate_export(
    *,
    fmt="jpeg",
    long_edge=None,
    quality=None,
    srgb=False,
    exif=False,
    text=None,
    logo=None,
    corner="bottom-right",
    width_pct=18,
    opacity=65,
):
    if fmt not in {"jpeg", "png"} or (
        quality is not None and (fmt != "jpeg" or not 1 <= quality <= 100)
    ):
        raise ValueError("JPEG 质量范围为 1–100；PNG 不接受质量参数")
    if long_edge is not None and not 1 <= long_edge <= 65535:
        raise ValueError("导出长边需为 1–65535 像素")
    if sum((text is not None, logo is not None, exif)) > 1:
        raise ValueError("文字、logo、拍摄参数水印只能选一种")
    if text is not None and (
        not text.strip() or len(text) > 240 or not text.isprintable()
    ):
        raise ValueError("请输入 1–240 个可打印字符")
    if not (1 <= width_pct <= 60 and 1 <= opacity <= 100) or corner not in {
        "top-left",
        "top-right",
        "bottom-left",
        "bottom-right",
    }:
        raise ValueError("水印位置、宽度或透明度无效")
    if logo is not None and not Path(logo).is_file():
        raise ValueError("找不到 PNG logo")


def paint_mark(canvas, text, logo, corner, width_pct, opacity):
    from PIL import Image, ImageDraw, ImageFont

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
    return [x, y, mark.width, mark.height]


def capture_caption(image):
    tags = image.getexif()
    capture = tags.get_ifd(34665)
    parts = []
    for label in (tags.get(272), capture.get(42036)):
        if isinstance(label, str) and label.strip():
            parts.append(" ".join(label.split())[:80])
    for tag, pattern in (
        (37386, "{:g} mm"),
        (33437, "f/{:g}"),
        (33434, None),
        (34855, "ISO {:g}"),
    ):
        try:
            number = float(capture[tag])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        if not math.isfinite(number) or number <= 0:
            continue
        if pattern:
            parts.append(pattern.format(number))
        elif number < 0.5 and math.isclose(1 / number, round(1 / number), rel_tol=0.01):
            parts.append(f"1/{round(1 / number)} s")
        else:
            parts.append(f"{number:g} s")
    if not parts:
        raise ValueError("照片缺少可显示的 EXIF 拍摄参数")
    return "  ·  ".join(parts)


def export_image(
    source,
    out,
    *,
    fmt="jpeg",
    long_edge=None,
    quality=None,
    srgb=False,
    exif=False,
    text=None,
    logo=None,
    corner="bottom-right",
    width_pct=18,
    opacity=65,
):
    try:
        from PIL import Image, ImageCms, ImageOps
    except ImportError as exc:
        raise ValueError("SDR 导出需要 Pillow") from exc
    validate_export(
        fmt=fmt,
        long_edge=long_edge,
        quality=quality,
        srgb=srgb,
        exif=exif,
        text=text,
        logo=logo,
        corner=corner,
        width_pct=width_pct,
        opacity=opacity,
    )
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
        alpha = original.mode == "RGBA" or "transparency" in original.info
        if fmt == "jpeg" and alpha:
            raise ValueError("带透明通道的输入请选择 PNG 输出")
        if exif:
            text = capture_caption(original)
        canvas = ImageOps.exif_transpose(original)
        if alpha:
            canvas = canvas.convert("RGBA")
        if canvas.mode == "L":
            canvas = canvas.convert("RGB")
        profile = original.info.get("icc_profile")
    if long_edge is not None:
        canvas.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    if srgb:
        target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        if profile:
            try:
                canvas = ImageCms.profileToProfile(
                    canvas, io.BytesIO(profile), target_profile, outputMode=canvas.mode
                )
            except ImageCms.PyCMSError as exc:
                raise ValueError("无法将源 ICC 转换至 sRGB") from exc
        profile = target_profile.tobytes()
    marked = text is not None or logo is not None
    box = paint_mark(canvas, text, logo, corner, width_pct, opacity) if marked else None
    out.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if fmt == "jpeg" else "png"
    target = out / (
        source.stem
        + ("-watermark-" if marked else "-export-")
        + uuid.uuid4().hex[:12]
        + "."
        + ext
    )
    # Save orientation-normalized pixels and the source color profile. Omit capture metadata.
    canvas.info.clear()
    opts = {"icc_profile": profile} if profile is not None else {}
    if fmt == "jpeg":
        opts.update(quality=quality if quality is not None else 95, subsampling=0)
    with tempfile.TemporaryDirectory(dir=out) as folder:
        staged = Path(folder) / ("image." + ext)
        canvas.save(staged, **opts)
        os.link(staged, target)
    return {
        "output": str(target),
        "pixels": list(canvas.size),
        "mark_box": box,
        "engine": "Pillow",
        **({"caption": text} if exif else {}),
    }


def stamp(source, out, *, text=None, logo=None, exif=False, **options):
    if sum((text is not None, logo is not None, exif)) != 1:
        raise ValueError("请选择文字或透明 PNG logo")
    return export_image(source, out, text=text, logo=logo, exif=exif, **options)
