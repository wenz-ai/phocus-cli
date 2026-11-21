"""Round dust corrections in Phocus RAW sensor pixel coordinates."""
import math


def dust_args(rows):
    spots = []
    centers = set()
    for row in rows or []:
        x, y, radius, amount = map(float, row)
        if not (
            math.isfinite(x)
            and math.isfinite(y)
            and min(x, y) >= 0
            and 5 <= radius <= 200
            and 1 <= amount <= 10
        ):
            raise ValueError("除尘需要非负像素坐标、5–200 像素半径及 1–10 的强度")
        if (x, y) in centers:
            raise ValueError("同一次调用中的除尘点中心不能重复")
        centers.add((x, y))
        spots.append((x, y, radius, amount))
    return spots


def read_dust_spots(settings):
    return [
        dict(x=p["X"], y=p["Y"], radius=p["Radius"], amount=p["Amount"])
        for p in settings.get("DustPoints", [])
        if isinstance(p, dict)
        and p.get("Type") == 0
        and {"X", "Y", "Radius", "Amount"} <= p.keys()
    ]


def apply_dust_spots(settings, raw, spots):
    from PIL import Image

    size = settings.get("AdjustmentLayers") or {}
    width, height = size.get("Width", 0), size.get("Height", 0)
    if not (width > 0 and height > 0):
        raise ValueError("原图的传感器尺寸缺失")
    with raw.open("rb") as stream:
        exif = Image.Exif()
        exif.load_from_fp(stream)
        serial = exif.get(50735) or exif.get_ifd(34665).get(42033)
    if not isinstance(serial, str) or not serial.strip():
        raise ValueError("RAW 未提供相机序列号，无法绑定原生除尘数据")
    points = settings.get("DustPoints", [])
    if not isinstance(points, list) or len(points) != settings.get("DustPointCount", 0):
        raise ValueError("已有除尘记录不完整")
    if points and settings.get("DustSerialNumber") != serial:
        raise ValueError("已有除尘记录与当前机身不匹配")
    for x, y, radius, amount in spots:
        if x >= width or y >= height:
            raise ValueError("除尘点超出未裁切原图边界")
        matches = [p for p in points if p.get("X") == x and p.get("Y") == y]
        if matches:
            p = matches[0]
            if (
                len(matches) != 1
                or p.get("Type") != 0
                or p.get("streamableVersion") != 1
            ):
                raise ValueError("同位置已有其他类型的除尘记录")
            p.update(Radius=radius, Amount=amount)
        else:
            points.append(
                dict(
                    X=x, Y=y, Radius=radius, Amount=amount, Type=0, streamableVersion=1
                )
            )
    settings.update(
        DustPoints=points,
        DustPointCount=len(points),
        DustSerialNumber=serial,
        ApplyDustRemoval=True,
    )
