"""Quick test: show pattern on the Waveshare 1.3" OLED HAT."""
import time

from luma.core.interface.serial import spi
from luma.core.render import canvas
from luma.oled.device import sh1106

serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
device = sh1106(serial)
device.contrast(255)

# Test 1: white fill using canvas
print("Test 1: white fill...")
with canvas(device) as draw:
    draw.rectangle((0, 0, 127, 63), fill="white")
time.sleep(3)

# Test 2: pattern with text
print("Test 2: pattern + text...")
with canvas(device) as draw:
    draw.rectangle((0, 0, 127, 63), outline="white")
    draw.rectangle((4, 4, 123, 15), fill="white")
    draw.rectangle((4, 48, 123, 59), fill="white")
    draw.text((20, 25), "HELLO KILNPI", fill="white")
time.sleep(5)

print("Done!")
