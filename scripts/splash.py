#!/usr/bin/env python3
"""Show an animated splash screen tracking system boot progress.

Run as kilnpi-splash.service (Type=simple). Shows a progress bar that
fills as system services come online. Exits when the main app signals
readiness via a sentinel file, at which point the app takes over the display.
"""

import os
import subprocess
import time
from pathlib import Path

from luma.core.interface.serial import spi  # type: ignore[import-untyped]
from luma.core.render import canvas  # type: ignore[import-untyped]
from luma.oled.device import sh1106  # type: ignore[import-untyped]
from PIL import ImageFont  # type: ignore[import-untyped]

SENTINEL = Path("/tmp/kilnpi-ready")
SENTINEL.unlink(missing_ok=True)

# System milestones to track, in rough boot order.
# The splash runs as a system service (after local-fs.target), so we can
# watch later targets come up.  The sentinel file signals the app is ready.
MILESTONES = [
    ("sysinit.target", "System init"),
    ("network.target", "Network"),
    ("network-online.target", "Online"),
    ("multi-user.target", "Services"),
]

serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
device = sh1106(serial)
device.contrast(255)
font = ImageFont.load_default()


def is_active(unit: str) -> bool:
    """Check if a systemd unit is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def draw(label: str, done: int, total: int) -> None:
    filled = int((done / total) * 16)
    bar = "\u2588" * filled + "\u2591" * (16 - filled)
    with canvas(device) as draw_ctx:
        draw_ctx.text((0, 14), "    KilnPi", fill="white", font=font)
        draw_ctx.text((0, 28), f" {bar}", fill="white", font=font)
        draw_ctx.text((0, 42), f" {label}...", fill="white", font=font)


total = len(MILESTONES) + 1  # +1 for "Ready"
reached = 0

# Track which milestones have been reached (they stay reached)
milestone_done = [False] * len(MILESTONES)

for _ in range(120):  # max 60s (120 × 0.5s)
    if SENTINEL.exists():
        draw("Ready!", total, total)
        time.sleep(0.5)
        # Skip luma cleanup so the display stays lit until the main app takes over
        os._exit(0)

    # Check each milestone in order
    for i, (unit, label) in enumerate(MILESTONES):
        if not milestone_done[i] and is_active(unit):
            milestone_done[i] = True

    reached = sum(milestone_done)
    # Show the label of the next pending milestone
    current_label = "Waiting"
    for i, (_, label) in enumerate(MILESTONES):
        if not milestone_done[i]:
            current_label = label
            break
    else:
        current_label = "App loading"

    draw(current_label, reached, total)
    time.sleep(0.5)

# If we get here (timeout), keep display lit
os._exit(0)
