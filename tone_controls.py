"""Native Phocus histogram and selective color settings (sidecar 31 / correction 11)."""

CHANNELS = ("rgb", "red", "green", "blue")
GAMMA = ("Gamma", "GammaRed", "GammaGreen", "GammaBlue")
BAND_KEYS = (
    "SelectiveSrcH",
    "SelectiveSrcL",
    "SelectiveSrcS",
    "SelectiveAngle",
    "SelectiveDstH",
    "SelectiveDstL",
    "SelectiveDstS",
)
HUE_NAMES = {
    "red": 0,
    "orange": 30,
    "yellow": 60,
    "green": 120,
    "cyan": 180,
    "blue": 240,
    "purple": 270,
    "magenta": 300,
}


def levels_args(rows):
    levels = {}
    for channel, black, mid, white in rows or ():
        if channel not in CHANNELS or channel in levels:
            raise ValueError("色阶通道为 rgb、red、green 或 blue，每通道只写一次")
        black, mid, white = int(black), float(mid), int(white)
        if not (0 <= black < white <= 255 and 0.1 <= mid <= 4.0):
            raise ValueError("色阶需要 0 ≤ 黑场 < 白场 ≤ 255，中间调为 0.1–4")
        levels[channel] = [black, mid, white]
    return levels


def apply_levels(settings, levels):
    shadows, highlights = settings.get("Shadow"), settings.get("Highlight")
    if not (
        isinstance(shadows, list)
        and isinstance(highlights, list)
        and len(shadows) == len(highlights) == 4
        and all(k in settings for k in GAMMA)
    ):
        raise ValueError("无法识别当前 .phos 色阶结构")
    for index, channel in enumerate(CHANNELS):
        entry = levels.get(channel, levels.get("rgb"))
        if entry is not None:
            black, mid, white = entry
            shadows[index] = black * 64
            highlights[index] = white * 64
            settings[GAMMA[index]] = 1 + mid
    settings["ApplyHistogram"] = True


def inspect_levels(settings):
    shadows, highlights = settings.get("Shadow", []), settings.get("Highlight", [])
    return {
        name: [round(black / 64), round(settings[gamma] - 1, 4), round(white / 64)]
        for name, black, white, gamma in zip(CHANNELS, shadows, highlights, GAMMA)
        if gamma in settings
    }


def hue_difference(first, second):
    return (first - second + 180) % 360 - 180


def bands_args(rows):
    bands = []
    for hue, width, shift, saturation, lightness in rows or ():
        center = HUE_NAMES[hue] if hue in HUE_NAMES else float(hue)
        width, shift, saturation, lightness = map(
            float, (width, shift, saturation, lightness)
        )
        if not (
            0 <= center < 360
            and 1 <= width <= 90
            and -45 <= shift <= 45
            and 0.3 <= saturation <= 1.7
            and -50 <= lightness <= 50
        ):
            raise ValueError(
                "选色范围：中心 0–<360°、宽度 1–90°、色相偏移 ±45°、饱和度 0.3–1.7、明度 ±50"
            )
        if any(abs(hue_difference(center, b[0])) < 0.0001 for b in bands):
            raise ValueError("同一色相中心只能指定一次")
        bands.append([center, width, shift, saturation, lightness])
    return bands


def band_arrays(settings):
    arrays = [settings.get(k) for k in BAND_KEYS]
    if (
        not all(isinstance(a, list) for a in arrays)
        or len({len(a) for a in arrays}) != 1
    ):
        raise ValueError("无法识别当前 .phos 的分色记录")
    return arrays


def apply_bands(settings, bands, clear=False):
    arrays = band_arrays(settings)
    if clear:
        for a in arrays:
            a.clear()
    for center, width, shift, saturation, lightness in bands:
        index = next(
            (
                i
                for i, v in enumerate(arrays[0])
                if abs(hue_difference(v, center)) < 0.0001
            ),
            None,
        )
        if index is None:
            # A new point starts with the same source coordinates as Phocus's hue wheel.
            for a, v in zip(arrays, (center, 0.5, 1.0, width, center, 0.5, 0.0)):
                a.append(v)
            index = len(arrays[0]) - 1
        arrays[3][index] = width
        arrays[4][index] = (arrays[0][index] + shift) % 360
        arrays[5][index] = arrays[1][index] * saturation
        arrays[6][index] = lightness
    if bands:
        settings["ApplyCC"] = True


def inspect_bands(settings):
    if not any(k in settings for k in BAND_KEYS):
        return []
    return [
        {
            "hue": round(h, 4),
            "width": round(width, 4),
            "shift": round(hue_difference(dst_h, h), 4),
            "saturation": round(dst_l / src_l, 4) if src_l else None,
            "lightness": round(dst_s, 4),
        }
        for h, src_l, _src_s, width, dst_h, dst_l, dst_s in zip(*band_arrays(settings))
    ]


def sample_color(path, x, y, radius=4):
    """Estimate the hue of a displayed patch, using oriented sRGB pixels."""
    import colorsys
    import io
    from PIL import Image, ImageOps, ImageCms, ImageStat

    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 <= radius <= 64):
        raise ValueError("取样坐标使用 0–1，半径使用 0–64 像素")
    Image.MAX_IMAGE_PIXELS = 155_000_000
    with Image.open(path) as image:
        if (
            image.format not in {"JPEG", "PNG"}
            or image.mode not in {"RGB", "L"}
            or getattr(image, "n_frames", 1) != 1
            or "mp" in image.info
            or "transparency" in image.info
            or b"hdrgm:" in image.info.get("xmp", b"")
        ):
            raise ValueError("请使用普通 SDR JPEG 或不透明 RGB PNG 预览取样")
        if image.format == "PNG":
            with path.open("rb") as header:
                data = header.read(25)
                if len(data) != 25 or data[24] != 8:
                    raise ValueError("取样仅支持 8 位 PNG")
        view = ImageOps.exif_transpose(image)
        px, py = round(x * (view.width - 1)), round(y * (view.height - 1))
        box = (
            max(0, px - radius),
            max(0, py - radius),
            min(view.width, px + radius + 1),
            min(view.height, py + radius + 1),
        )
        patch = view.crop(box)
        profile = image.info.get("icc_profile")
        if profile:
            try:
                patch = ImageCms.profileToProfile(
                    patch,
                    io.BytesIO(profile),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            except ImageCms.PyCMSError as e:
                raise ValueError("预览 ICC 无法转换到 sRGB") from e
        rgb = [v / 255 for v in ImageStat.Stat(patch.convert("RGB")).mean]
    hue, saturation, brightness = colorsys.rgb_to_hsv(*rgb)
    reliable = (max(rgb) - min(rgb)) >= 0.025
    return {
        "pixel": [px, py],
        "box": list(box),
        "rgb": [round(v * 255) for v in rgb],
        "estimated_hue": round(hue * 360, 2) % 360 if reliable else None,
        "saturation": round(saturation, 4),
        "value": round(brightness, 4),
    }
