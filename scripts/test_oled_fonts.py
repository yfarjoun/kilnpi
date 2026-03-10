#!/usr/bin/env python3
"""Test OLED font rendering: regular, bold, and inverse.

Usage (on the Pi — stop kilnpi service first!):
    sudo systemctl --user stop kilnpi.service
    uv run python scripts/test_oled_fonts.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from luma.core.interface.serial import spi  # type: ignore[import-untyped]
from luma.core.render import canvas  # type: ignore[import-untyped]
from luma.oled.device import sh1106  # type: ignore[import-untyped]
from PIL import ImageFont  # type: ignore[import-untyped]

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_SIZE = 10
LINE_H = 14


def load_font(name: str) -> ImageFont.FreeTypeFont | None:
    path = f"{FONT_DIR}/{name}"
    try:
        return ImageFont.truetype(path, FONT_SIZE)
    except OSError:
        print(f"  Font not found: {path}")
        return None


def main() -> None:
    print("Initializing OLED...")
    serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
    device = sh1106(serial)
    device.contrast(255)

    regular = load_font("DejaVuSansMono.ttf")
    bold = load_font("DejaVuSansMono-Bold.ttf")
    fallback = ImageFont.load_default()

    font_r = regular or fallback
    font_b = bold or fallback

    print(f"Regular font: {font_r}")
    print(f"Bold font:    {font_b}")

    # Screen 1: Compare regular vs bold
    print("\nScreen 1: Regular vs Bold (5 seconds)...")
    with canvas(device) as draw:
        draw.text((0, 0 * LINE_H), "Regular 25.3C", fill="white", font=font_r)
        draw.text((0, 1 * LINE_H), "Bold 25.3C", fill="white", font=font_b)
        draw.text((0, 2 * LINE_H), "Regular ABCDEF", fill="white", font=font_r)
        draw.text((0, 3 * LINE_H), "Bold ABCDEF", fill="white", font=font_b)
    time.sleep(5)

    # Screen 2: Inverse (white bg, black text)
    print("Screen 2: Inverse lines (5 seconds)...")
    with canvas(device) as draw:
        draw.text((0, 0 * LINE_H), "Normal line", fill="white", font=font_r)
        # Inverse line
        draw.rectangle([(0, 1 * LINE_H), (device.width, 2 * LINE_H)], fill="white")
        draw.text((0, 1 * LINE_H), "Inverse line", fill="black", font=font_r)
        draw.text((0, 2 * LINE_H), "Normal line", fill="white", font=font_r)
        # Inverse + bold
        draw.rectangle([(0, 3 * LINE_H), (device.width, 4 * LINE_H)], fill="white")
        draw.text((0, 3 * LINE_H), "Inverse+Bold", fill="black", font=font_b)
    time.sleep(5)

    # Screen 3: Mixed — simulates real display
    print("Screen 3: Simulated compact view (5 seconds)...")
    with canvas(device) as draw:
        draw.text((0, 0 * LINE_H), "D:45% M:60% CPU:55C", fill="white", font=font_r)
        draw.text((0, 1 * LINE_H), "10.0.0.5 W+ B+ MB+", fill="white", font=font_r)
        draw.text((0, 2 * LINE_H), "Poll: 2s ago", fill="white", font=font_r)
        # Bold + inverse for running status
        draw.rectangle([(0, 3 * LINE_H), (device.width, 4 * LINE_H)], fill="white")
        draw.text((0, 3 * LINE_H), "Bisque S1 850/900", fill="black", font=font_b)
    time.sleep(5)

    # Clear display
    print("Clearing display...")
    with canvas(device) as draw:
        pass  # blank

    print("Done.")


if __name__ == "__main__":
    main()
