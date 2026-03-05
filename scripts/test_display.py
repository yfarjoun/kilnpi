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

# Then: show text on black background
print("Showing text...")
image = Image.new("1", (device.width, device.height), "black")
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, 127, 63), outline="white")
draw.text((10, 25), "Hello KilnPi!", fill="white")
device.display(image)
print("Done! Display should show text with border.")
