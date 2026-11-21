"""Use the unmodified Windows Phocus 4.2 RGB24 frame renderer in a local worker."""

import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from xml.etree import ElementTree

IMAGE = "phocus-local/windows-frames:4.2-v1"
CONTEXT = "colima-phocus-frames"
STYLES = dict(
    zip(
        [f"hasselblad-{i}" for i in range(1, 8)] + ["explorer-1", "explorer-2"],
        [12, 6, 7, 1, 2, 3, 4, 8, 9],
    )
)
LENSES = {
    "XCD 21": "XCD 4,0 / 21",
    "XCD 25V": "XCD 2,5 / 25V",
    "XCD 30": "XCD 3,5 / 30",
    "XCD 38V": "XCD 2,5 / 38V",
    "XCD 45": "XCD 3,5 / 45",
    "XCD 45P": "XCD 4 / 45P",
    "XCD 28P": "XCD 4 / 28P",
    "XCD 55V": "XCD 2,5 / 55V",
    "XCD 65": "XCD 2,8 / 65",
    "XCD 80": "XCD 1,9 / 80",
    "XCD 90V": "XCD 2,5 / 90V",
    "XCD 90": "XCD 3,2 / 90",
    "XCD 120": "XCD 3,5 / 120 MACRO",
    "XCD 135": "XCD 2,8 / 135",
    "XCD 20-35E": "XCD 3,2-4,5 / 20-35E",
    "XCD 35-75": "XCD 3,5-4,5 / 35-75",
    "XCD 75P": "XCD 75P",
    "XCD 35-100E": "XCD 2,8-4 / 35-100E",
    "XCD 90 II": "XCD 2,5 / 90V",
    "XCD 38": "XCD 2,5 / 38V",
    "XCD 55": "XCD 2,5 / 55V",
}
# Additional bodies recognized by the PC 4.2 selector; keep serials out of reports.
EDITION_EXCEPTIONS = (
    "e36243fc4550968fa526e8ae88b823ac2f499839160f385322d13f29a1fbbd8d",
    "2af35b16bcb82ffff85c8827a3605135bd61eec5b8e6cd96cf1f21104bf8042e",
    "041e7f74e0116b8e10cebfac89bdecdd16f8e58e69fa464a369f020a11acd9bd",
)
STYLE_MARK = "Phocus CLI PC4.2 frame/"


def style_list():
    return {
        "engine": "Hasselblad Phocus for Windows 4.2 / RenderPhotoFramePreview",
        "formats": "8-bit SDR JPEG",
        "styles": [
            {"name": k, "id": v, "earth_explorer_only": k.startswith("explorer-")}
            for k, v in STYLES.items()
        ],
    }


def edition_serial(exif, capture, xmp):
    serial = capture.get(42033) or exif.get(50735)
    if not serial and xmp:
        try:
            doc = ElementTree.fromstring(xmp.rstrip(b"\x00"))
            key = "{http://ns.adobe.com/exif/1.0/aux/}SerialNumber"
            serial = next(
                (
                    n.get(key) or n.text
                    for n in doc.iter()
                    if n.get(key) or n.tag == key
                ),
                None,
            )
        except ElementTree.ParseError:
            pass
    if not serial:
        # Hasselblad ImageUniqueID encodes the body identifier before the frame counter.
        uid = str(capture.get(42016, ""))
        if re.fullmatch(r"0{12}[0-9a-fA-F]{20}", uid):
            code = bytes.fromhex(uid[12:16])
            if code.isalpha():
                serial = code.decode("ascii") + str(int(uid[16:24], 16)).zfill(8)
    return str(serial or "").strip()


def select_styles(requested, explorer):
    available = [s for s in STYLES if explorer or not s.startswith("explorer-")]
    if list(requested) == ["all"]:
        return available
    if (
        not requested
        or len(set(requested)) != len(requested)
        or any(s not in STYLES for s in requested)
    ):
        raise ValueError("请选择不重复的款式名称，或单独使用 all")
    if any(s not in available for s in requested):
        raise ValueError("Explorer 款式要求保留 Earth Explorer 机身信息的原始照片")
    return list(requested)


def numeric(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def prepare(source, requested, long_edge):
    from PIL import Image, ImageCms, ImageOps

    Image.MAX_IMAGE_PIXELS = 155_000_000
    with Image.open(source) as im:
        xmp = im.info.get("xmp", b"")
        if (
            im.format != "JPEG"
            or im.mode not in ("L", "RGB")
            or getattr(im, "n_frames", 1) != 1
            or "mp" in im.info
            or b"hdrgm:" in xmp
        ):
            raise ValueError(
                "官方画框接口仅接受未加框的 SDR JPEG；请先从 RAW 导出带 EXIF 的 JPEG 母版"
            )
        exif = im.getexif()
        capture = exif.get_ifd(34665)
        camera = str(exif.get(272, "")).strip()
        make = str(exif.get(271, "")).strip()
        if not camera or "hasselblad" not in (make + " " + camera).lower():
            raise ValueError("无法从输入 EXIF 确认哈苏机型")
        if str(exif.get(305, "")).startswith(STYLE_MARK) or re.search(
            rb"AppliedPhotoFrameStyle[^\d]{1,12}[1-9]", xmp
        ):
            raise ValueError("图像已有画框，请选未加框的母版")
        serial = edition_serial(exif, capture, xmp)
        styles = select_styles(
            requested,
            serial.startswith("YT24")
            or hashlib.sha256(serial.encode()).hexdigest() in EDITION_EXCEPTIONS,
        )
        while camera.casefold().startswith("hasselblad "):
            camera = camera[11:].strip()
        model = "Hasselblad " + camera if camera.casefold() != "hasselblad" else camera
        lens = str(capture.get(42036, "")).split("@")[0].strip()
        if not lens or lens.lower() in ("unknown", "hc 9", "xcd 0"):
            lens = "Third Party Lens"
        elif lens.startswith("XCD"):
            lens = LENSES.get(lens, "Third Party Lens")
        aperture = numeric(capture.get(33437))
        seconds = numeric(capture.get(33434))
        iso = numeric(capture.get(34855))
        shutter = (
            "-"
            if seconds is None
            else (
                f"1/{round(1 / seconds)}s"
                if seconds < 0.5
                and math.isclose(round(1 / seconds), 1 / seconds, rel_tol=0.01)
                else f"{seconds:g}s"
            )
        )
        meta = [
            model,
            lens,
            f"f/{aperture:.1f}" if aperture else "-",
            shutter,
            f"{iso:g}" if iso else "-",
        ]
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        work = ImageOps.exif_transpose(im)
        if long_edge:
            work.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
        if im.info.get("icc_profile"):
            try:
                work = ImageCms.profileToProfile(
                    work, io.BytesIO(im.info["icc_profile"]), profile, outputMode="RGB"
                )
            except ImageCms.PyCMSError as err:
                raise ValueError("输入色彩配置无法转换至 sRGB") from err
        else:
            work = work.convert("RGB")
    return work, styles, meta, profile.tobytes()


def render_frames(source, out, requested, long_edge=None, quality=95):
    from PIL import Image

    if long_edge is not None and not 1 <= long_edge <= 65535 or not 1 <= quality <= 100:
        raise ValueError("长边或 JPEG 质量超出范围")
    if not shutil.which("docker"):
        raise ValueError("本机尚未安装可选的 Windows 画框引擎，请阅读 docs/frames.md")
    endpoint = subprocess.run(
        [
            "docker",
            "context",
            "inspect",
            CONTEXT,
            "--format",
            "{{.Endpoints.docker.Host}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if endpoint.returncode or not endpoint.stdout.strip().startswith("unix://"):
        raise ValueError("本机专用画框环境未配置，请先运行 phocus frames setup")
    if subprocess.run(
        ["docker", "--context", CONTEXT, "info", "--format", "{{.ID}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode:
        if not shutil.which("colima"):
            raise ValueError("无法启动专用 Colima 环境")
        start = subprocess.run(
            ["colima", "start", "phocus-frames", "--activate=false"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if start.returncode:
            raise ValueError("画框环境启动失败：" + start.stderr[-600:])
    work, styles, metadata, icc = prepare(source, requested, long_edge)
    out.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "--context",
        CONTEXT,
        "run",
        "--rm",
        "--pull=never",
        "--network",
        "none",
        "--platform",
        "linux/amd64",
        "-i",
        IMAGE,
    ]
    with tempfile.TemporaryDirectory(prefix=".frames-", dir=out) as folder:
        staging = Path(folder)
        result = staging / "frames"
        result.mkdir()
        with (
            tempfile.TemporaryFile(dir=staging) as input_stream,
            tempfile.TemporaryFile(dir=staging) as frames,
            tempfile.TemporaryFile() as log,
        ):
            header = {
                "styles": [STYLES[k] for k in styles],
                "metadata": metadata,
                "size": work.size,
            }
            input_stream.write(json.dumps(header).encode() + b"\n")
            # Strip-by-strip avoids a second full-size copy of a 100MP RGB image.
            for top in range(0, work.height, 256):
                input_stream.write(
                    work.crop(
                        (0, top, work.width, min(work.height, top + 256))
                    ).tobytes()
                )
            work.close()
            input_stream.seek(0)
            try:
                proc = subprocess.run(
                    command,
                    stdin=input_stream,
                    stdout=frames,
                    stderr=log,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError("Windows 画框渲染超时") from exc
            if proc.returncode:
                log.seek(0)
                reason = log.read()[-1600:].decode(errors="replace").strip()
                raise ValueError(
                    f"Windows 画框引擎未完成：{reason}。可用 colima start phocus-frames --activate=false 启动已安装的环境"
                )
            frames.seek(0)
            rows = []
            for k in styles:
                style, w, h = json.loads(frames.readline(1024))
                if style != STYLES[k] or min(w, h) < 1 or w * h * 3 > 2_147_483_647:
                    raise ValueError("Windows 引擎返回了无效画布")
                image = Image.new("RGB", (w, h))
                for top in range(0, h, 256):
                    height = min(256, h - top)
                    block = frames.read(w * height * 3)
                    if len(block) != w * height * 3:
                        raise ValueError("Windows 画框像素不完整")
                    image.paste(Image.frombytes("RGB", (w, height), block), (0, top))
                name = source.stem + "-" + k + ".jpg"
                tags = Image.Exif()
                tags[305] = STYLE_MARK + k
                image.save(
                    result / name,
                    quality=quality,
                    subsampling=0,
                    icc_profile=icc,
                    exif=tags,
                )
                image.close()
                rows.append({"style": k, "pixels": [w, h], "name": name})
            if frames.read(1):
                raise ValueError("Windows 引擎输出与请求数量不同")
        final = out / (source.stem + "-frames-" + uuid.uuid4().hex[:12])
        os.rename(result, final)
    for row in rows:
        row["output"] = str(final / row.pop("name"))
    return {
        "source": str(source),
        "engine": "PhocusApi64.dll / RenderPhotoFramePreview",
        "frames": rows,
    }
