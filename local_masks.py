"""Native exposure masks stored inside the current Phocus adjustment version."""


def linear_args(rows):
    masks = []
    for name, *items in rows or []:
        if not name.strip() or len(name) > 90 or not name.isprintable():
            raise ValueError("蒙版名称需为 1–90 个可打印字符")
        if any(m["name"] == name for m in masks):
            raise ValueError("同一次调用中的蒙版不能重名")
        x0, y0, x1, y1, ev = map(float, items)
        if not all(0 <= n <= 1 for n in (x0, y0, x1, y1)) or (x0, y0) == (x1, y1):
            raise ValueError("渐变端点须在 0–1 内且两点不能重合")
        if not -4 <= ev <= 4:
            raise ValueError("局部曝光范围为 −4 至 +4 EV")
        masks.append({"name": name, "full": [x0, y0], "zero": [x1, y1], "ev": ev})
    return masks


def point(coords):
    return {"PointX": coords[0], "PointY": coords[1], "streamableVersion": 1}


def put_linear(settings, masks):
    container = settings.get("AdjustmentLayers")
    if not isinstance(container, dict) or container.get("streamableVersion") != 1:
        raise ValueError("无法识别该 .phos 的调节层格式")
    layers = container.setdefault("Layers", [])
    if not isinstance(layers, list) or not all(
        isinstance(layer, dict) for layer in layers
    ):
        raise ValueError("调节层记录不完整")
    for mask in masks:
        matches = [layer for layer in layers if layer.get("Name") == mask["name"]]
        if matches:
            layer = matches[0]
            if (
                len(matches) != 1
                or layer.get("LayerType") != 0
                or len(layer.get("GradientList", [])) != 1
                or any(
                    k
                    not in {
                        "Active",
                        "EV",
                        "GradientList",
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
            gradient = layer["GradientList"][0]
            if (
                not isinstance(gradient, dict)
                or not {"From", "To"} <= gradient.keys()
                or set(gradient) - {"From", "To", "streamableVersion"}
            ):
                raise ValueError("同名蒙版类型不符")
        else:
            gradient = {"streamableVersion": 1}
            layer = {
                "Name": mask["name"],
                "Active": True,
                "LayerType": 0,
                "LayerID": "",
                "MaskInvert": False,
                "fStartPointX": -1.0,
                "fStartPointY": -1.0,
                "GradientList": [gradient],
                "streamableVersion": 1,
            }
            layers.append(layer)
        # The native To endpoint receives the full EV, From receives zero.
        gradient.update(To=point(mask["full"]), From=point(mask["zero"]))
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
        report.append(entry)
    return report
