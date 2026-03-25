import neopixel
import machine
import time
import math

# Configuration
NUM_LEDS   = 10
PIN        = 13
TOUCH_PIN  = 4
FRAME_MS   = 20    # Fixed frame time in ms (~50 fps)
TOUCH_THRESHOLD = 400  # Below this = touched

# Speed expressed as hue-degrees advanced per second
SPEED_NORMAL = 100.0   # normal:  ~1 full cycle / 3.6 s
SPEED_FAST   = 400.0   # fast:    4× normal

# Smoothing: how many seconds to reach the new speed
LERP_DURATION = 1.0
# Per-frame lerp factor derived from duration and frame time
LERP_ALPHA = 1.0 - math.exp(-FRAME_MS / 1000.0 / LERP_DURATION)

np       = neopixel.NeoPixel(machine.Pin(PIN), NUM_LEDS, bpp=4)
touchpad = machine.TouchPad(machine.Pin(TOUCH_PIN))

def hsv_to_rgbw(h, s, v):
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

    r, g, b = r + m, g + m, b + m
    w = min(r, g, b)
    r, g, b = r - w, g - w, b - w

    return (int(r * 255), int(g * 255), int(b * 255), int(w * 255))

def is_touched():
    return touchpad.read() < TOUCH_THRESHOLD

offset       = 0.0
current_speed = SPEED_NORMAL   # degrees/second, smoothly interpolated

while True:
    target_speed = SPEED_FAST if is_touched() else SPEED_NORMAL

    # Exponential lerp: glides toward target, fastest at start, slows near end
    current_speed += (target_speed - current_speed) * LERP_ALPHA

    # Advance offset by the fraction of a second this frame represents
    degrees_this_frame = current_speed * (FRAME_MS / 1000.0)
    offset = (offset + degrees_this_frame) % 360

    for i in range(NUM_LEDS):
        hue = (i * 360 / NUM_LEDS + offset) % 360
        np[i] = hsv_to_rgbw(hue, 1.0, 1.0)

    np.write()
    time.sleep_ms(FRAME_MS)