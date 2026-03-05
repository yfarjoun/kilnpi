"""Quick test: show 'Hello KilnPi!' on the Waveshare 1.3" OLED HAT."""
from luma.core.interface.serial import spi
from luma.oled.device import sh1106
from PIL import Image, ImageDraw

serial = spi(device=0, port=0, gpio_DC=24, gpio_RST=25)
device = sh1106(serial)

image = Image.new("1", (device.width, device.height), "black")
draw = ImageDraw.Draw(image)
draw.text((10, 25), "Hello KilnPi!", fill="white")
device.display(image)
print("Display updated!")
