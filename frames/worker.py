"""Runs in Windows Python inside the local Wine container. Writes framed RGB only."""

import ctypes
import json
import os
import sys
from pathlib import Path


def main():
    import msvcrt
    import winreg

    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    src, dst = sys.stdin.buffer, sys.stdout.buffer
    limits = 155_000_000
    request = json.loads(src.readline(16384))
    w, h = request["size"]
    if min(w, h) < 1 or w * h > limits:
        raise ValueError("image dimensions")
    pix = src.read(w * h * 3)
    if len(pix) != w * h * 3:
        raise ValueError("truncated RGB")
    app = Path(r"Z:\opt\phocus")
    os.chdir(app)
    # Register the image's locally installed compatibility fonts with DirectWrite.
    font_root = Path(r"C:\windows\Fonts")
    with winreg.CreateKey(
        winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    ) as k:
        for title, file in [("Tahoma", "tahoma.ttf"), ("Tahoma Bold", "tahomabd.ttf")]:
            winreg.SetValueEx(k, title + " (TrueType)", 0, winreg.REG_SZ, file)
            ctypes.windll.gdi32.AddFontResourceW(str(font_root / file))
    ctypes.windll.ole32.CoInitializeEx(None, 2)
    with os.add_dll_directory(str(app)):
        dll = ctypes.WinDLL(str(app / "PhocusApi64.dll"))
        size = dll.GetPhotoFramePreviewSize
        integer = ctypes.c_int
        size.argtypes = [integer] * 3 + [ctypes.POINTER(integer)] * 2
        render = dll.RenderPhotoFramePreview
        render.argtypes = (
            [integer, ctypes.c_void_p, integer, integer, integer]
            + [ctypes.c_wchar_p] * 5
            + [ctypes.c_void_p, integer]
        )
        for style in request["styles"]:
            ow, oh = integer(), integer()
            rc = size(style, w, h, ctypes.byref(ow), ctypes.byref(oh))
            n = ow.value * oh.value * 3
            if rc or min(ow.value, oh.value) <= 0 or not 0 < n <= 2_147_483_647:
                raise RuntimeError(f"GetPhotoFramePreviewSize({style}): {rc}")
            out = ctypes.create_string_buffer(n)
            rc = render(style, pix, w, h, w * 3, *request["metadata"], out, n)
            if rc:
                raise RuntimeError(
                    f"RenderPhotoFramePreview({style}): 0x{rc & 0xFFFFFFFF:08x}"
                )
            dst.write(json.dumps([style, ow.value, oh.value]).encode() + b"\n")
            dst.write(memoryview(out).cast("B"))
            del out
    dst.flush()


if __name__ == "__main__":
    main()
