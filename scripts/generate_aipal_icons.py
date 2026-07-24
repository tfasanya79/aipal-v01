#!/usr/bin/env python3
"""Generate AiPal orb launcher icons (logo gold/green on dark)."""
from __future__ import annotations

import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("pip install Pillow")

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "apps" / "mobile"
BRAND = MOBILE / "assets" / "brand"
BG = (13, 17, 23, 255)
GOLD = (255, 200, 21)
WARM_GOLD = (232, 168, 56)
LOGO_GREEN = (0, 59, 43)


def draw_orb(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    for r, color, alpha in [
        (size * 0.46, LOGO_GREEN, 120),
        (size * 0.34, WARM_GOLD, 210),
        (size * 0.22, (255, 220, 160), 255),
    ]:
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rr = int(r)
        c = (*color, alpha)
        ld.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=c)
        img = Image.alpha_composite(img, layer)
    # subtle voice arc
    arc_r = int(size * 0.38)
    draw.arc(
        (cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r),
        start=300,
        end=20,
        fill=(*GOLD, 210),
        width=max(2, size // 64),
    )
    return img


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    master = draw_orb(1024)
    master_path = BRAND / "aipal_icon_1024.png"
    master.save(master_path)

    densities = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    res = MOBILE / "android" / "app" / "src" / "main" / "res"
    for folder, px in densities.items():
        out = res / folder / "ic_launcher.png"
        draw_orb(px).save(out)

    web_icons = MOBILE / "web" / "icons"
    web_icons.mkdir(parents=True, exist_ok=True)
    draw_orb(192).save(web_icons / "Icon-192.png")
    draw_orb(512).save(web_icons / "Icon-512.png")
    draw_orb(192).save(web_icons / "Icon-maskable-192.png")
    draw_orb(512).save(web_icons / "Icon-maskable-512.png")
    draw_orb(48).save(MOBILE / "web" / "favicon.png")
    ios_icons = MOBILE / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    if ios_icons.exists():
        ios_sizes = {
            "Icon-App-20x20@1x.png": 20,
            "Icon-App-20x20@2x.png": 40,
            "Icon-App-20x20@3x.png": 60,
            "Icon-App-29x29@1x.png": 29,
            "Icon-App-29x29@2x.png": 58,
            "Icon-App-29x29@3x.png": 87,
            "Icon-App-40x40@1x.png": 40,
            "Icon-App-40x40@2x.png": 80,
            "Icon-App-40x40@3x.png": 120,
            "Icon-App-60x60@2x.png": 120,
            "Icon-App-60x60@3x.png": 180,
            "Icon-App-76x76@1x.png": 76,
            "Icon-App-76x76@2x.png": 152,
            "Icon-App-83.5x83.5@2x.png": 167,
            "Icon-App-1024x1024@1x.png": 1024,
        }
        for filename, px in ios_sizes.items():
            draw_orb(px).save(ios_icons / filename)
    print(f"Wrote {master_path} and launcher/web icons")


if __name__ == "__main__":
    main()
