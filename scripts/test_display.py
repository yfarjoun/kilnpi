"""Quick test: show 'Hello KilnPi!' on the Waveshare 1.3" OLED HAT."""
import time

from luma.core.interface.serial import spi
from luma.oled.device import sh1106
from PIL import Image, ImageDraw

serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
device = sh1106(serial)
device.contrast(255)

# First: fill screen white to confirm display works
print("Filling screen white...")
image = Image.new("1", (device.width, device.height), "white")
device.display(image)
time.sleep(2)

# Then: show large filled rectangles and text
print("Showing pattern...")
image = Image.new("1", (device.width, device.height), "black")
draw = ImageDraw.Draw(image)
# Thick border
draw.rectangle((0, 0, 127, 63), outline="white")
draw.rectangle((2, 2, 125, 61), outline="white")
# Filled bars at top and bottom
draw.rectangle((4, 4, 123, 15), fill="white")
draw.rectangle((4, 48, 123, 59), fill="white")
# Text in the middle
draw.text((20, 25), "HELLO KILNPI", fill="white")
device.display(image)
print("Done! Should show bars at top/bottom with text in middle.")
