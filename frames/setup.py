"""Prepare a private Docker image from the official Phocus 4.2 installer on this Mac."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
IMAGE = "phocus-local/windows-frames:4.2-v1"
CONTEXT = "colima-phocus-frames"
VENDOR = (
    "https://cdn.hasselblad.com/software/Phocus_for_PC/4.2/Phocus-4.2-x64.exe",
    "d93fbaa8571d6c97bf5f930ae856241731cbf11b661b5b9fdc500f16ac85536a",
)
PYTHON = (
    "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
    "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3",
)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def get_asset(path, spec, tmp):
    url, expected = spec
    if path is None:
        path = tmp / url.rsplit("/", 1)[-1]
        subprocess.run(
            ["curl", "-fL", "--retry", "3", "--retry-all-errors", url, "-o", path],
            check=True,
        )
    if digest(path) != expected:
        raise ValueError("安装文件 SHA-256 不符：" + path.name)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--python-zip", type=Path)
    args = parser.parse_args()
    for tool in ("docker", "colima", "cabextract", "msiextract"):
        if not shutil.which(tool):
            raise ValueError(
                "缺少 "
                + tool
                + "。准备工具：brew install docker colima cabextract msitools"
            )
    with tempfile.TemporaryDirectory(prefix="phocus-official-") as folder:
        tmp = Path(folder)
        exe = get_asset(args.installer, VENDOR, tmp)
        python = get_asset(args.python_zip, PYTHON, tmp)
        cab = tmp / "app.cab"
        # WiX attached container in this exact, hash-verified vendor build.
        with exe.open("rb") as f, cab.open("wb") as out:
            f.seek(865736)
            size = 1_223_806_709
            while size:
                part = f.read(min(size, 4 * 1024 * 1024))
                if not part:
                    raise ValueError("Windows 安装包不完整")
                out.write(part)
                size -= len(part)
        subprocess.run(["cabextract", "-q", "-F", "a1", "-d", tmp, cab], check=True)
        cab.unlink()
        expand = tmp / "expanded"
        expand.mkdir()
        subprocess.run(
            ["msiextract", "-C", expand, tmp / "a1"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        build = tmp / "build"
        build.mkdir()
        for rel, expected in json.loads((ROOT / "manifest.json").read_text()).items():
            src = expand / "Hasselblad/Phocus 4.2" / rel
            if digest(src) != expected:
                raise ValueError("Windows 组件不匹配：" + rel)
            dest = build / "phocus" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        with zipfile.ZipFile(python) as archive:
            archive.extractall(build / "python")
        for name in ("Dockerfile", "worker.py"):
            shutil.copyfile(ROOT / name, build / name)
        subprocess.run(
            [
                "colima",
                "start",
                "phocus-frames",
                "--activate=false",
                "--vm-type",
                "vz",
                "--vz-rosetta",
                "--cpu",
                "3",
                "--memory",
                "4",
                "--disk",
                "16",
                "--mount",
                "none",
            ],
            check=True,
        )
        env = {**os.environ, "DOCKER_BUILDKIT": "0"}
        subprocess.run(
            [
                "docker",
                "--context",
                CONTEXT,
                "build",
                "--platform",
                "linux/amd64",
                "-t",
                IMAGE,
                build,
            ],
            check=True,
            env=env,
        )
    print("Phocus Windows 4.2 画框引擎已就绪。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        sys.exit(str(e))
