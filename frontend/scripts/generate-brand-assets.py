#!/usr/bin/env python3
"""
Generate the social share image and PWA/touch icons from the KritiFin brand
mark (the same geometry as components/BrandLogo.tsx, viewBox 0 0 40 40).

Deterministic and dependency-light: uses pymupdf from the backend venv.

    backend/.venv/bin/python frontend/scripts/generate-brand-assets.py

Outputs (frontend/public/):
    og-image.png          1200x630 social card (og:image / twitter:image)
    icon-512.png          PWA icon
    icon-192.png          PWA icon
    apple-touch-icon.png  180x180
    favicon-32.png        PNG favicon fallback (SVG data-URI stays primary)
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

PUBLIC = Path(__file__).resolve().parents[1] / "public"

# Brand palette (matches tailwind theme + BrandLogo.tsx)
SLATE_950 = (15 / 255, 23 / 255, 42 / 255)  # #0F172A
SLATE_800 = (30 / 255, 41 / 255, 59 / 255)  # #1E293B
SLATE_400 = (148 / 255, 163 / 255, 184 / 255)  # #94A3B8
BRAND_600 = (37 / 255, 99 / 255, 235 / 255)  # #2563EB
BLUE_300 = (147 / 255, 197 / 255, 253 / 255)  # #93C5FD
WHITE = (1, 1, 1)


def draw_monogram(shape: pymupdf.Shape, x: float, y: float, box: float) -> None:
    """The K mark from BrandLogo.tsx scaled from its 40x40 viewBox."""
    f = box / 40.0
    width = 3.6 * f

    shape.draw_line(pymupdf.Point(x + 13 * f, y + 9 * f), pymupdf.Point(x + 13 * f, y + 31 * f))
    shape.finish(color=WHITE, width=width, lineCap=1, lineJoin=1)

    shape.draw_polyline(
        [
            pymupdf.Point(x + 28 * f, y + 10 * f),
            pymupdf.Point(x + 15 * f, y + 20 * f),
            pymupdf.Point(x + 28 * f, y + 30 * f),
        ]
    )
    shape.finish(color=WHITE, width=width, lineCap=1, lineJoin=1)

    shape.draw_circle(pymupdf.Point(x + 27.5 * f, y + 10.5 * f), 2.4 * f)
    shape.finish(color=None, fill=BLUE_300)


def render(page: pymupdf.Page, path: Path) -> None:
    pix = page.get_pixmap(alpha=False)
    pix.save(path)
    print(f"wrote {path.relative_to(PUBLIC.parent.parent)} ({pix.width}x{pix.height})")


def og_image() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=630)
    shape = page.new_shape()

    # Background + soft brand glows
    shape.draw_rect(page.rect)
    shape.finish(color=None, fill=SLATE_950)
    shape.draw_circle(pymupdf.Point(1080, 40), 420)
    shape.finish(color=None, fill=BRAND_600, fill_opacity=0.22)
    shape.draw_circle(pymupdf.Point(80, 640), 320)
    shape.finish(color=None, fill=BRAND_600, fill_opacity=0.12)

    # Brand mark card
    mark_box = 168.0
    mx, my = 96.0, 150.0
    shape.draw_rect(pymupdf.Rect(mx, my, mx + mark_box, my + mark_box), radius=0.24)
    shape.finish(color=SLATE_800, width=2, fill=SLATE_800)
    draw_monogram(shape, mx, my + 6, mark_box - 12)
    shape.commit()

    page.insert_text(
        pymupdf.Point(300, 245),
        "KritiFin",
        fontsize=96,
        fontname="hebo",
        color=WHITE,
    )
    page.insert_text(
        pymupdf.Point(302, 300),
        "The AI operating system for financial advisers",
        fontsize=32,
        fontname="helv",
        color=SLATE_400,
    )
    for i, line in enumerate(
        (
            "Morning briefings  ·  Meeting prep  ·  AI Copilot",
            "Consumer Duty compliance  ·  Client 360",
        )
    ):
        page.insert_text(
            pymupdf.Point(96, 440 + i * 44),
            line,
            fontsize=26,
            fontname="helv",
            color=(0.75, 0.81, 0.89),
        )
    render(page, PUBLIC / "og-image.png")
    doc.close()


def icon(size: int, name: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=size, height=size)
    shape = page.new_shape()
    # Full-bleed dark tile (iOS/Android mask their own corners).
    shape.draw_rect(page.rect)
    shape.finish(color=None, fill=SLATE_950)
    shape.draw_circle(pymupdf.Point(size * 0.82, size * 0.16), size * 0.5)
    shape.finish(color=None, fill=BRAND_600, fill_opacity=0.35)
    draw_monogram(shape, 0, 0, size)
    shape.commit()
    render(page, PUBLIC / name)
    doc.close()


def main() -> None:
    PUBLIC.mkdir(exist_ok=True)
    og_image()
    icon(512, "icon-512.png")
    icon(192, "icon-192.png")
    icon(180, "apple-touch-icon.png")
    icon(32, "favicon-32.png")


if __name__ == "__main__":
    main()
