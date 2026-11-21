"""Paint and erase round strokes in Phocus's native 16-bit mask tiles."""
import base64
import io
import math


def stroke_args(rows):
    strokes = []
    for row in rows or []:
        if not 5 <= len(row) <= 260:
            raise ValueError("笔画须包含层名、paint/erase、半径、EV 及 1–256 个 X:Y 点")
        name, mode, radius, ev, *points = row
        radius, ev = float(radius), float(ev)
        if not name.strip() or not name.isprintable() or len(name) > 90:
            raise ValueError("画笔图层名须为 1–90 个可打印字符")
        if mode not in ("paint", "erase") or not (0 < radius <= 0.5 and -4 <= ev <= 4):
            raise ValueError("模式为 paint/erase，半径为短边的 (0,0.5]，EV 为 −4 至 +4")
        path = []
        for point in points:
            x, y = map(float, point.split(":"))
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError("笔画坐标为 0–1")
            path.append((x, y))
        strokes.append((name, mode, radius, ev, path))
    return strokes


def paint_tiles(tiles, width, height, path, radius, mode):
    from PIL import Image, ImageDraw

    radius = max(1, round(radius * min(width, height)))
    points = [(round(x * (width - 1)), round(y * (height - 1))) for x, y in path]
    xs, ys = zip(*points)
    box = (
        max(0, min(xs) - radius),
        max(0, min(ys) - radius),
        min(width, max(xs) + radius + 1),
        min(height, max(ys) + radius + 1),
    )
    stroke = Image.new("L", (box[2] - box[0], box[3] - box[1]))
    draw = ImageDraw.Draw(stroke)
    local = [(x - box[0], y - box[1]) for x, y in points]
    if len(local) > 1:
        draw.line(local, fill=255, width=2 * radius + 1)
    for x, y in local:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)

    cols = math.ceil(width / 256)
    for ty in range(box[1] // 256, (box[3] - 1) // 256 + 1):
        for tx in range(box[0] // 256, (box[2] - 1) // 256 + 1):
            x, y = tx * 256 - box[0], ty * 256 - box[1]
            mask = stroke.crop((x, y, x + 256, y + 256))
            if not mask.getbbox():
                continue
            index = ty * cols + tx
            previous = tiles[index].strip()
            if previous:
                with Image.open(io.BytesIO(base64.b64decode(previous))) as image:
                    if (
                        image.size != (256, 256)
                        or image.mode != "I;16"
                        or image.format != "PNG"
                    ):
                        raise ValueError("画笔图块格式不受支持")
                    tile = image.convert("I")
            else:
                tile = Image.new("I", (256, 256))
            tile.paste(65535 if mode == "paint" else 0, (0, 0, 256, 256), mask)
            if tile.getbbox():
                buf = io.BytesIO()
                tile.convert("I;16").save(buf, format="PNG")
                tiles[index] = base64.b64encode(buf.getvalue()).decode("ascii")
            else:
                tiles[index] = " " if index == 0 else ""


def apply_strokes(settings, strokes):
    c = settings.get("AdjustmentLayers", {})
    if c.get("streamableVersion") != 1 or c.get("TileFactor") != 2:
        raise ValueError("需要 Phocus 的 2 倍采样原生画笔蒙版格式")
    w, h = c.get("Width", 0), c.get("Height", 0)
    if not (
        isinstance(w, int)
        and isinstance(h, int)
        and min(w, h) > 0
        and w * h <= 155_000_000
    ):
        raise ValueError("原始蒙版尺寸缺失或超出范围")
    width, height = (w + 1) // 2, (h + 1) // 2
    count = math.ceil(width / 256) * math.ceil(height / 256)
    layers = c.setdefault("Layers", [])
    for name, mode, radius, ev, points in strokes:
        matches = [l for l in layers if l.get("Name") == name]
        if len(matches) > 1:
            raise ValueError("画笔图层名称不唯一")
        if matches:
            layer = matches[0]
            tiles = layer.get("TileStringList")
            if (
                layer.get("LayerType") != 2
                or layer.get("MaskInvert")
                or layer.get("streamableVersion") != 1
                or not isinstance(tiles, list)
                or len(tiles) != count
                or not all(isinstance(v, str) for v in tiles)
            ):
                raise ValueError("同名图层不是可编辑的普通画笔层")
        else:
            if mode == "erase":
                raise ValueError("橡皮擦需要已有的画笔图层")
            tiles = [" "] + [""] * (count - 1)
            layer = dict(
                Name=name,
                Active=True,
                LayerType=2,
                LayerID="",
                MaskInvert=False,
                fStartPointX=-1.0,
                fStartPointY=-1.0,
                TileStringList=tiles,
                streamableVersion=1,
            )
            layers.append(layer)
        paint_tiles(tiles, width, height, points, radius, mode)
        layer.update(Active=True, EV=ev)
    settings["ApplyAdjustmentLayers"] = True
