"""Native exposure masks stored inside the current Phocus adjustment version."""


import math


# Phocus adjustment layer slider units, measured on Mac 4.2.3.
LAYER_FIELDS = {
    "temperature": ("Temp", -100, 100),
    "tint": ("Tint", -100, 100),
    "highlights": ("Recovery", -100, 100),
    "shadows": ("Shadow", -100, 100),
    "saturation": ("Saturation", -100, 100),
    "clarity": ("Clarity", -100, 100),
    "sharpness": ("Sharpness", -500, 500),
    "moire": ("Moire", -5, 5),
}
NATIVE_LAYER_FIELDS = {field for field, _, _ in LAYER_FIELDS.values()}


def layer_adjustments(rows):
    result = {}
    for name, key, raw in rows or []:
        if key not in LAYER_FIELDS:
            raise ValueError("可用图层参数：" + ", ".join(LAYER_FIELDS))
        value = float(raw)
        _, low, high = LAYER_FIELDS[key]
        if not low <= value <= high:
            raise ValueError(f"{key} 范围为 {low}–{high}")
        changes = result.setdefault(name, {})
        if key in changes:
            raise ValueError(f"同一图层参数重复：{name} {key}")
        changes[key] = value
    return result


def apply_layer_adjustments(settings, edits):
    container = settings.get("AdjustmentLayers") or {}
    if container.get("streamableVersion") != 1:
        raise ValueError("无法识别调节层格式")
    for name, changes in edits.items():
        matches = [
            layer for layer in container.get("Layers", []) if layer.get("Name") == name
        ]
        if (
            len(matches) != 1
            or matches[0].get("streamableVersion") != 1
            or matches[0].get("LayerType") not in (0, 2)
        ):
            raise ValueError(f"需要唯一的原生调节层：{name}")
        for key, value in changes.items():
            matches[0][LAYER_FIELDS[key][0]] = value


def _validate_name(name, masks):
    if not name.strip() or len(name) > 90 or not name.isprintable():
        raise ValueError("蒙版名称需为 1–90 个可打印字符")
    if any(mask["name"] == name for mask in masks):
        raise ValueError("同一次调用中的蒙版不能重名")


def linear_args(rows):
    masks = []
    for name, *items in rows or []:
        _validate_name(name, masks)
        x0, y0, x1, y1, ev = map(float, items)
        if not all(0 <= n <= 1 for n in (x0, y0, x1, y1)) or (x0, y0) == (x1, y1):
            raise ValueError("渐变端点须在 0–1 内且两点不能重合")
        if not -4 <= ev <= 4:
            raise ValueError("局部曝光范围为 −4 至 +4 EV")
        masks.append({"name": name, "full": [x0, y0], "zero": [x1, y1], "ev": ev})
    return masks


def radial_args(rows):
    masks = []
    for name, cx, cy, rx, ry, angle, feather, side, ev in rows or []:
        _validate_name(name, masks)
        cx, cy, rx, ry, angle, feather, ev = map(
            float, (cx, cy, rx, ry, angle, feather, ev)
        )
        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < rx <= 1 and 0 < ry <= 1):
            raise ValueError("中心坐标为 0–1，两个半径均须大于 0 且不超过 1")
        if not (-180 <= angle <= 180 and 0 <= feather <= 1 and -4 <= ev <= 4):
            raise ValueError("角度为 −180 至 180°，羽化为 0–1，曝光为 −4 至 +4 EV")
        if side not in ("inside", "outside"):
            raise ValueError("请选择 inside 或 outside")
        masks.append(
            dict(
                name=name,
                center=[cx, cy],
                radii=[rx, ry],
                angle=angle,
                feather=feather,
                side=side,
                ev=ev,
            )
        )
    return masks


def point(coords):
    return {"PointX": coords[0], "PointY": coords[1], "streamableVersion": 1}


def put_masks(settings, masks):
    container = settings.get("AdjustmentLayers")
    if not isinstance(container, dict) or container.get("streamableVersion") != 1:
        raise ValueError("无法识别该 .phos 的调节层格式")
    layers = container.setdefault("Layers", [])
    if not isinstance(layers, list) or not all(
        isinstance(layer, dict) for layer in layers
    ):
        raise ValueError("调节层记录不完整")
    for mask in masks:
        if "center" in mask:
            key = "EllipseList"
            shape = dict(
                Center=point(mask["center"]),
                RadiusX=mask["radii"][0],
                RadiusY=mask["radii"][1],
                Rotation=math.radians(mask["angle"]),
                Feather=mask["feather"],
                Invert=mask["side"] == "outside",
            )
        else:
            key = "GradientList"
            shape = dict(To=point(mask["full"]), From=point(mask["zero"]))
        matches = [layer for layer in layers if layer.get("Name") == mask["name"]]
        if matches:
            layer = matches[0]
            if (
                len(matches) != 1
                or layer.get("LayerType") != 0
                or len(layer.get(key, [])) != 1
                or any(
                    k
                    not in NATIVE_LAYER_FIELDS
                    | {
                        "Active",
                        "EV",
                        key,
                        "LayerID",
                        "LayerType",
                        "MaskInvert",
                        "Name",
                        "fStartPointX",
                        "fStartPointY",
                        "streamableVersion",
                    }
                    for k in layer
                )
                or layer.get("MaskInvert")
            ):
                raise ValueError("同名图层含其他设置；请为新渐变另取名称")
            previous = layer[key][0]
            if (
                not isinstance(previous, dict)
                or previous.get("streamableVersion", 1) != 1
                or set(previous) - {"streamableVersion"} != set(shape)
            ):
                raise ValueError("同名蒙版类型不符")
        else:
            layer = {
                "Name": mask["name"],
                "Active": True,
                "LayerType": 0,
                "LayerID": "",
                "MaskInvert": False,
                "fStartPointX": -1.0,
                "fStartPointY": -1.0,
                "streamableVersion": 1,
            }
            layers.append(layer)
        layer[key] = [dict(shape, streamableVersion=1)]
        layer.update(Active=True, EV=mask["ev"])
    settings["ApplyAdjustmentLayers"] = True


def inspect_masks(settings):
    layers = settings.get("AdjustmentLayers", {}).get("Layers", [])
    report = []
    for layer in layers:
        entry = {
            "name": layer.get("Name"),
            "active": layer.get("Active"),
            "ev": layer.get("EV", 0),
            "inverted": layer.get("MaskInvert", False),
        }
        edits = {
            key: layer[field]
            for key, (field, _, _) in LAYER_FIELDS.items()
            if field in layer
        }
        if edits:
            entry["adjustments"] = edits
        if layer.get("LayerType") == 2 and isinstance(layer.get("TileStringList"), list):
            entry["brush"] = {"painted_tiles": sum(bool(tile.strip()) for tile in layer["TileStringList"] if isinstance(tile, str))}
        gradients = []
        for g in layer.get("GradientList", []):
            if all(
                isinstance(g.get(k), dict) and {"PointX", "PointY"} <= g[k].keys()
                for k in ("From", "To")
            ):
                gradients.append(
                    {
                        "full": [g["To"]["PointX"], g["To"]["PointY"]],
                        "zero": [g["From"]["PointX"], g["From"]["PointY"]],
                    }
                )
        if gradients:
            entry["linear"] = gradients
        radial = []
        for ellipse in layer.get("EllipseList", []):
            try:
                center = ellipse["Center"]
                radial.append(
                    dict(
                        center=[center["PointX"], center["PointY"]],
                        radii=[ellipse["RadiusX"], ellipse["RadiusY"]],
                        angle=math.degrees(ellipse["Rotation"]),
                        feather=ellipse["Feather"],
                        side="outside" if ellipse["Invert"] else "inside",
                    )
                )
            except (KeyError, TypeError):
                continue
        if radial:
            entry["radial"] = radial
        report.append(entry)
    return report
