import neopixel
import machine
import time
import math

# Configuration
NUM_LEDS = 10
PIN = 13
DELAY_MS = 1  # Delay between frames (ms) — lower = faster

np = neopixel.NeoPixel(machine.Pin(PIN), NUM_LEDS, bpp=4)

def hsv_to_rgbw(h, s, v):
    """
    Convert HSV (0–360, 0–1, 0–1) to RGBW tuple.
    White channel is derived from the minimum RGB component.
    """
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if   h < 60:  r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x

    r, g, b = (r + m), (g + m), (b + m)

    # Extract white from shared minimum, keeping colors vivid
    w = min(r, g, b)
    r, g, b = r - w, g - w, b - w

    return (
        int(r * 255),
        int(g * 255),
        int(b * 255),
        int(w * 255)
    )

offset = 0

while True:
    for i in range(NUM_LEDS):
        # Spread the full 360° hue spectrum across all LEDs,
        # then shift it over time using `offset`
        hue = (i * 360 / NUM_LEDS + offset) % 360
        np[i] = hsv_to_rgbw(hue, 1.0, 1.0)

    np.write()

    offset = (offset + 2) % 360  # Advance gradient position
    time.sleep_ms(DELAY_MS)