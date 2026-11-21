"""Render with the real Phocus hot folder and compare decoded, full-resolution samples."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageChops, ImageStat

CLI = Path(__file__).resolve().parents[1] / "phocus"


def samples(path):
    with Image.open(path) as img:
        w, h = img.size
        tiles = Image.new("RGB", (256 * 4, 256 * 4))
        for row in range(4):
            for col in range(4):
                left = (w - 256) * (2 * col + 1) // 8
                top = (h - 256) * (2 * row + 1) // 8
                tile = img.crop((left, top, left + 256, top + 256)).convert("RGB")
                tiles.paste(tile, (256 * col, 256 * row))
        return tiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--watch", required=True)
    parser.add_argument("--spool", required=True)
    args = parser.parse_args()
    # Pillow warns for large decoded images. Allow the documented 100MP test case.
    Image.MAX_IMAGE_PIXELS = 150_000_000
    recipes = {
        "exposure": 1,
        "contrast": 15,
        "brightness": 10,
        "highlights": 40,
        "shadows": 30,
        "temperature": 6500,
        "tint_native": 0.015,
        "saturation": -30,
        "vibrance": 30,
        "clarity": 40,
        "detail": 8,
        "sharpen_amount": 180,
        "grain_amount": 85,
        "grain_size": 90,
        "grain_roughness": 85,
        "noise_filter_bias": 10,
        "color_noise_radius": 40,
        "moire_removal": 5,
        "remove_checkerboard": 1,
        "sharpen_radius": 2.8,
        "sharpen_threshold": 20,
        "sharpen_dark_limit": 35,
        "grain_type": 2,
        "grain_color": 80,
        "lens_corrections": 1,
        "vignette_amount": 90,
        "defringe_purple": 80,
        "defringe_green": 80,
        "keystone_horizontal": 15,
        "keystone_vertical": 15,
        "keystone_aspect": 10,
        "mono_red": 60,
        "mono_green": 20,
        "mono_blue": 65,
        "monochrome": 1,
    }
    available = json.loads(subprocess.check_output([str(CLI), "capabilities"]))
    if recipes.keys() != available.keys():
        raise RuntimeError(
            "The verification recipes must cover every advertised adjustment."
        )
    with tempfile.TemporaryDirectory(prefix="phocus-verify-") as out:
        cached = {}

        def render(settings):
            key = tuple(sorted(settings.items()))
            if key not in cached:
                command = [
                    str(CLI),
                    "render",
                    str(args.raw),
                    "--watch",
                    args.watch,
                    "--spool",
                    args.spool,
                    "--out",
                    out,
                ]
                if settings:
                    command += ["--set", *(f"{k}={v}" for k, v in settings.items())]
                done = subprocess.run(
                    command, text=True, capture_output=True, check=False
                )
                if done.returncode:
                    raise RuntimeError(done.stdout or done.stderr)
                report = json.loads(done.stdout)[0]
                saved = json.loads(
                    subprocess.check_output([str(CLI), "inspect", report["sidecar"]])
                )["values"]
                if any(saved[k] != v for k, v in settings.items()):
                    raise RuntimeError(
                        f"Phocus did not retain requested values: {settings}"
                    )
                cached[key] = samples(report["output"]), report["elapsed_seconds"]
            return cached[key]

        issues = []
        for name, value in recipes.items():
            # Keep clarity and grain active in both variants when testing dependent sliders.
            base = {"clarity": 40} if name == "detail" else {}
            if name.startswith("grain_"):
                base = {"grain_amount": 40}
            # Define the baseline explicitly so existing edits don't silently cancel the test.
            neutral = {
                "temperature": 4200,
                "sharpen_radius": 1,
                "mono_red": 21,
                "mono_green": 72,
                "mono_blue": 7,
                "sharpen_amount": 60,
                "grain_amount": 40,
                "grain_size": 20,
                "grain_roughness": 20,
            }.get(name, 0)
            control = {**base, name: neutral}
            # If this file has already been staged by a previous test the saved state may vary.
            baseline, _ = render(control)
            variant, elapsed = render({**base, name: value})
            diff = ImageChops.difference(baseline, variant)
            mean = sum(ImageStat.Stat(diff).mean) / 3
            print(
                json.dumps(
                    {
                        "parameter": name,
                        "baseline": neutral,
                        "test": value,
                        "rgb_mean_absolute_difference": round(mean, 5),
                        "elapsed_seconds": elapsed,
                    }
                ),
                flush=True,
            )
            if not diff.getbbox():
                issues.append(name)
        if issues:
            raise SystemExit("No pixel difference in samples: " + ", ".join(issues))


if __name__ == "__main__":
    main()
