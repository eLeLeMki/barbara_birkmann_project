# =============================================================================
#  rover_wifi_joystick.py  –  ESP32 MicroPython Wi-Fi Rover  (Joystick UI)
# =============================================================================
#
#  HARDWARE REQUIREMENTS & SAFETY WARNINGS
#  ----------------------------------------
#  ⚠️  NEVER connect DC motors directly to ESP32 GPIO pins!
#      ESP32 GPIO pins can only supply ~12 mA safely.
#      Motors draw hundreds of milliamps – direct connection WILL damage the ESP32.
#
#  You MUST use a motor driver module between the ESP32 and motors.
#  Common options (all work with DIR + PWM wiring style used here):
#    • L298N  – dual H-bridge, handles 2A per channel, 5–35 V motor supply
#    • L9110S – dual H-bridge, 800 mA per channel, 2.5–12 V motor supply
#    • TB6612FNG – more efficient than L298N, 1.2A per channel
#    • DRV8833 – compact, 1.5A per channel
#
#  Typical wiring for each motor (repeat for all 4):
#    ESP32 DIR pin  ──►  Motor driver IN1 (or INA)
#    ESP32 PWM pin  ──►  Motor driver IN2 (or INB) -- OR separate PWM/EN pin
#    Motor driver OUT1/OUT2  ──►  Motor terminals
#    External battery (e.g. 4× AA or LiPo)  ──►  Motor driver VM/GND
#    ESP32 GND  ──►  Motor driver GND  (SHARED GROUND – this is essential!)
#
#  ⚠️  Share a common GND between the ESP32 and motor driver.
#      Without it, signals are meaningless and things may behave erratically.
#
#  ⚠️  Power the ESP32 separately (USB or its own regulator).
#      Motor switching causes voltage spikes that can reset or damage the ESP32.
#
# =============================================================================
#
#  HOW TO UPLOAD AND RUN WITH THONNY
#  -----------------------------------
#  1. Install Thonny: https://thonny.org  (free, works on Windows/Mac/Linux)
#
#  2. Flash MicroPython firmware to your ESP32 if you haven't already:
#       • Download the .bin from https://micropython.org/download/ESP32_GENERIC/
#       • In Thonny → Tools → Options → Interpreter
#         Select "MicroPython (ESP32)" and the correct COM/serial port
#       • Click "Install or update MicroPython" and follow the prompts
#
#  3. Open this file in Thonny.
#
#  4. Save it to the ESP32 AS "main.py":
#       File → Save as → MicroPython device → type "main.py" → OK
#     Saving as main.py means it will run automatically every time the ESP32 boots.
#
#  5. Press the ESP32 reset button (or power cycle it).
#     The shell in Thonny will print the AP IP address (usually 192.168.4.1).
#
#  6. On your phone: go to Wi-Fi settings, connect to "ESP32-Rover" (password: rover1234).
#
#  7. Open your phone browser and go to:  http://192.168.4.1
#     The joystick control page will load – drag the joystick to drive!
#
# =============================================================================

import network
import socket
import time
from machine import Pin, PWM

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION – change these if needed
# ─────────────────────────────────────────────────────────────────────────────

AP_SSID     = "ESP32-Rover"   # Wi-Fi network name your phone will see
AP_PASSWORD = "rover1234"     # Must be 8+ characters for WPA2; set "" for open network
AP_IP       = "192.168.4.1"   # The IP you open in the browser (this is the default)

PWM_FREQ    = 20000            # Hz – motor PWM frequency
FAILSAFE_MS = 500             # Stop motors if no command received for this many ms

# ─────────────────────────────────────────────────────────────────────────────
#  MOTOR SETUP
#  Each motor has:
#    "dir" – direction pin (HIGH = one way, LOW = other way)
#    "pwm" – PWM pin that controls speed (duty_u16: 0 = stop, 65535 = full speed)
# ─────────────────────────────────────────────────────────────────────────────

motors = [
    {
        "name": "Motor 1 (front-left)",
        "dir": Pin(5,  Pin.OUT),
        "pwm": PWM(Pin(17), freq=PWM_FREQ),
    },
    {
        "name": "Motor 2 (front-right)",
        "dir": Pin(4,  Pin.OUT),
        "pwm": PWM(Pin(16), freq=PWM_FREQ),
    },
    {
        "name": "Motor 3 (rear-left)",
        "dir": Pin(23, Pin.OUT),
        "pwm": PWM(Pin(18), freq=PWM_FREQ),
    },
    {
        "name": "Motor 4 (rear-right)",
        "dir": Pin(25, Pin.OUT),
        "pwm": PWM(Pin(19), freq=PWM_FREQ),
    },
]

# ─────────────────────────────────────────────────────────────────────────────
#  SAFE STARTUP – stop all motors immediately at boot
# ─────────────────────────────────────────────────────────────────────────────

for m in motors:
    m["pwm"].duty_u16(0)   # Zero duty cycle = motor stopped
    m["dir"].value(0)      # Direction pin low

print("Motors initialised and stopped.")

# Timestamp of the last command received (used by the failsafe)
last_command_ms = time.ticks_ms()


# ─────────────────────────────────────────────────────────────────────────────
#  MOTOR CONTROL FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def speed_to_duty(speed_pct):
    """Convert a 0-100 % speed value to a 16-bit duty cycle (0–65535)."""
    speed_pct = max(0, min(100, speed_pct))
    return int(speed_pct / 100 * 65535)


def set_motor(motor, direction, speed_pct):
    """
    Drive a single motor.

    motor     – one entry from the motors[] list
    direction – True = forward, False = reverse
    speed_pct – 0 to 100 (percentage of full speed)
    """
    motor["dir"].value(1 if direction else 0)
    motor["pwm"].duty_u16(speed_to_duty(speed_pct))


def stop_all():
    """Immediately stop every motor (duty cycle to 0)."""
    for m in motors:
        m["pwm"].duty_u16(0)


def set_left_side(speed):
    """
    Drive the two left-side motors.
    speed: -100 (full reverse) … 0 (stop) … +100 (full forward)
    """
    speed = max(-100, min(100, speed))
    if speed >= 0:
        set_motor(motors[0], True,  speed)   # front-left  forward
        set_motor(motors[2], True,  speed)   # rear-left   forward
    else:
        set_motor(motors[0], False, -speed)  # front-left  reverse
        set_motor(motors[2], False, -speed)  # rear-left   reverse


def set_right_side(speed):
    """
    Drive the two right-side motors.
    speed: -100 (full reverse) … 0 (stop) … +100 (full forward)
    """
    speed = max(-100, min(100, speed))
    if speed >= 0:
        set_motor(motors[1], True,  speed)   # front-right forward
        set_motor(motors[3], True,  speed)   # rear-right  forward
    else:
        set_motor(motors[1], False, -speed)  # front-right reverse
        set_motor(motors[3], False, -speed)  # rear-right  reverse


def drive_joystick(x, y):
    """
    Differential / tank-drive mixing from joystick axes.

    x : -100 … +100  (left = negative, right = positive)
    y : -100 … +100  (backward = negative, forward = positive)

    left_speed  = y + x
    right_speed = y - x

    Values are clamped to [-100, 100] after mixing.
    """
    left_speed  = y + x
    right_speed = y - x

    # Normalise so neither side exceeds ±100 while preserving ratio
    peak = max(abs(left_speed), abs(right_speed), 100)
    left_speed  = int(left_speed  * 100 / peak)
    right_speed = int(right_speed * 100 / peak)

    set_left_side(left_speed)
    set_right_side(right_speed)


# ─────────────────────────────────────────────────────────────────────────────
#  WI-FI ACCESS POINT SETUP
# ─────────────────────────────────────────────────────────────────────────────

print("Starting Wi-Fi access point...")

ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=3)  # authmode 3 = WPA2

while not ap.active():
    time.sleep(0.1)

print("Access point active!")
print("  SSID    : {}".format(AP_SSID))
print("  Password: {}".format(AP_PASSWORD))
print("  IP      : {}".format(ap.ifconfig()[0]))
print("  Open    : http://{} in your phone browser".format(ap.ifconfig()[0]))

# ─────────────────────────────────────────────────────────────────────────────
#  HTML PAGE  –  single-file, self-contained joystick controller
# ─────────────────────────────────────────────────────────────────────────────

HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>ESP32 Rover</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0a0a0a;
    --surface:   #141414;
    --border:    #252525;
    --border2:   #333;
    --accent:    #e8ff00;
    --accent2:   #b8cc00;
    --danger:    #ff3b30;
    --text:      #eeeeee;
    --muted:     #555;
    --muted2:    #444;
    --live:      #39ff8f;
    --font:      'Courier New', Courier, monospace;
    --joy-size:  min(72vw, 340px);
    --knob-size: calc(var(--joy-size) * 0.32);
  }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    overflow: hidden;
    touch-action: none;
    -webkit-user-select: none;
    user-select: none;
  }

  body {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px 18px;
    gap: 0;
    min-height: 100dvh;
  }

  /* ── Header ── */
  header {
    width: 100%;
    max-width: 420px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px;
  }

  .brand {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .brand-title {
    font-size: 0.8rem;
    letter-spacing: 0.25em;
    color: var(--accent);
    text-transform: uppercase;
  }
  .brand-sub {
    font-size: 0.55rem;
    color: var(--muted);
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  .telemetry {
    text-align: right;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .tele-row {
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .tele-row span {
    color: var(--text);
  }
  .tele-row span.live  { color: var(--live); }
  .tele-row span.warn  { color: var(--danger); }

  /* ── Status bar ── */
  .status-bar {
    width: 100%;
    max-width: 420px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
  }

  #state-label {
    font-size: 1.5rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    transition: color 0.1s;
  }
  #state-label.stopped  { color: var(--muted); }
  #state-label.moving   { color: var(--accent); }

  .axis-display {
    display: flex;
    gap: 10px;
  }
  .axis-pill {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 0.62rem;
    letter-spacing: 0.1em;
    color: var(--muted);
    min-width: 58px;
    text-align: center;
  }
  .axis-pill span { color: var(--text); }

  /* ── Joystick ── */
  .joy-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    width: 100%;
  }

  .joy-base {
    position: relative;
    width:  var(--joy-size);
    height: var(--joy-size);
    border-radius: 50%;
    background:
      radial-gradient(circle at 50% 50%,
        #1c1c1c 0%,
        #111 60%,
        #0a0a0a 100%);
    border: 2px solid var(--border2);
    box-shadow:
      0 0 0 1px #000,
      inset 0 2px 8px rgba(0,0,0,0.7),
      0 4px 32px rgba(0,0,0,0.6);
    cursor: grab;
    touch-action: none;
    flex-shrink: 0;
  }

  /* Cardinal tick marks */
  .joy-base::before {
    content: '';
    position: absolute;
    inset: 12%;
    border-radius: 50%;
    border: 1px dashed var(--border2);
    pointer-events: none;
  }

  /* Cross-hair lines */
  .joy-crosshair {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    overflow: hidden;
    pointer-events: none;
  }
  .joy-crosshair::before,
  .joy-crosshair::after {
    content: '';
    position: absolute;
    background: var(--border);
  }
  .joy-crosshair::before {
    width: 1px; height: 100%;
    left: 50%; top: 0;
    transform: translateX(-50%);
  }
  .joy-crosshair::after {
    height: 1px; width: 100%;
    top: 50%; left: 0;
    transform: translateY(-50%);
  }

  /* Cardinal labels */
  .joy-label {
    position: absolute;
    font-size: 0.55rem;
    letter-spacing: 0.2em;
    color: var(--muted2);
    text-transform: uppercase;
    pointer-events: none;
  }
  .joy-label.top    { top: 6%;  left: 50%; transform: translateX(-50%); }
  .joy-label.bottom { bottom: 6%; left: 50%; transform: translateX(-50%); }
  .joy-label.lft    { left: 6%; top: 50%;  transform: translateY(-50%); }
  .joy-label.rgt    { right: 6%; top: 50%; transform: translateY(-50%); }

  /* Dead-zone circle */
  .joy-deadzone {
    position: absolute;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.06);
    pointer-events: none;
    /* sized by JS to match DEAD_ZONE_PCT */
  }

  /* Knob */
  .joy-knob {
    position: absolute;
    width:  var(--knob-size);
    height: var(--knob-size);
    border-radius: 50%;
    background: radial-gradient(circle at 38% 35%,
      #3a3a3a 0%,
      #1e1e1e 55%,
      #111 100%);
    border: 2px solid #444;
    box-shadow:
      0 2px 12px rgba(0,0,0,0.8),
      0 0 0 1px #111,
      inset 0 1px 3px rgba(255,255,255,0.08);
    top:  50%;
    left: 50%;
    transform: translate(-50%, -50%);
    transition: box-shadow 0.1s;
    pointer-events: none;
    will-change: transform;
  }

  .joy-knob.active {
    border-color: var(--accent2);
    box-shadow:
      0 2px 20px rgba(232,255,0,0.25),
      0 0 0 1px #111,
      inset 0 1px 3px rgba(255,255,255,0.1);
  }

  /* Knob inner dot */
  .joy-knob::after {
    content: '';
    position: absolute;
    width: 28%;
    height: 28%;
    border-radius: 50%;
    background: var(--accent);
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    opacity: 0.7;
  }

  /* ── Motor bars (visual feedback) ── */
  .motor-bars {
    width: 100%;
    max-width: 420px;
    display: flex;
    gap: 10px;
    align-items: stretch;
  }

  .motor-bar-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .motor-bar-label {
    font-size: 0.55rem;
    letter-spacing: 0.15em;
    color: var(--muted);
    text-transform: uppercase;
    text-align: center;
  }
  .motor-bar-track {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    height: 10px;
    position: relative;
    overflow: hidden;
  }
  .motor-bar-fill {
    position: absolute;
    top: 0;
    height: 100%;
    width: 0%;
    background: var(--accent);
    border-radius: 4px;
    transition: width 0.08s, left 0.08s, background 0.1s;
  }
  /* Forward fill grows right from center; reverse grows left */
  .motor-bar-fill.fwd  { left: 50%; }
  .motor-bar-fill.rev  { right: 50%; background: var(--danger); }

  /* ── Footer ── */
  footer {
    width: 100%;
    max-width: 420px;
    text-align: center;
    font-size: 0.55rem;
    color: var(--muted);
    letter-spacing: 0.12em;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-title">&#x25B6; ESP32 ROVER</div>
    <div class="brand-sub">Joystick Mode / MicroPython</div>
  </div>
  <div class="telemetry">
    <div class="tele-row">PING&nbsp;<span id="ping-val">--</span></div>
    <div class="tele-row">SPD&nbsp;<span id="spd-val">0</span>%</div>
  </div>
</header>

<div class="status-bar">
  <div id="state-label" class="stopped">STOP</div>
  <div class="axis-display">
    <div class="axis-pill">X&nbsp;<span id="x-val">0</span></div>
    <div class="axis-pill">Y&nbsp;<span id="y-val">0</span></div>
  </div>
</div>

<div class="joy-wrap">
  <div class="joy-base" id="joy-base">
    <div class="joy-crosshair"></div>
    <div class="joy-label top">FWD</div>
    <div class="joy-label bottom">BWD</div>
    <div class="joy-label lft">L</div>
    <div class="joy-label rgt">R</div>
    <div class="joy-deadzone" id="joy-deadzone"></div>
    <div class="joy-knob"  id="joy-knob"></div>
  </div>
</div>

<div class="motor-bars">
  <div class="motor-bar-wrap">
    <div class="motor-bar-label">LEFT</div>
    <div class="motor-bar-track">
      <div class="motor-bar-fill fwd" id="bar-l-fwd"></div>
      <div class="motor-bar-fill rev" id="bar-l-rev"></div>
    </div>
  </div>
  <div class="motor-bar-wrap">
    <div class="motor-bar-label">RIGHT</div>
    <div class="motor-bar-track">
      <div class="motor-bar-fill fwd" id="bar-r-fwd"></div>
      <div class="motor-bar-fill rev" id="bar-r-rev"></div>
    </div>
  </div>
</div>

<footer>DRAG JOYSTICK TO DRIVE &nbsp;|&nbsp; RELEASE TO STOP</footer>

<script>
// ── Constants ────────────────────────────────────────────────────────────────
const DEAD_ZONE_PCT  = 12;   // % of radius – ignore movements smaller than this
const SEND_INTERVAL  = 120;  // ms – how often to repeat command while held
const FAILSAFE_PAD   = 350;  // ms – must be less than ESP32 FAILSAFE_MS (500)

// ── DOM refs ─────────────────────────────────────────────────────────────────
const base      = document.getElementById('joy-base');
const knob      = document.getElementById('joy-knob');
const deadzone  = document.getElementById('joy-deadzone');
const stateEl   = document.getElementById('state-label');
const pingEl    = document.getElementById('ping-val');
const spdEl     = document.getElementById('spd-val');
const xEl       = document.getElementById('x-val');
const yEl       = document.getElementById('y-val');
const barLF     = document.getElementById('bar-l-fwd');
const barLR     = document.getElementById('bar-l-rev');
const barRF     = document.getElementById('bar-r-fwd');
const barRR     = document.getElementById('bar-r-rev');

// ── State ─────────────────────────────────────────────────────────────────────
let active      = false;
let originX     = 0, originY = 0;   // center of base in page coords
let radius      = 0;                // usable radius in px
let sendTimer   = null;
let lastJoyX    = 0, lastJoyY = 0; // last sent values (-100..100)
let inFlight    = false;            // rate-limit: one fetch at a time

// ── Size the dead-zone ring ───────────────────────────────────────────────────
function sizeDeadZone() {
  const r  = base.getBoundingClientRect();
  radius   = r.width / 2;
  originX  = r.left + radius;
  originY  = r.top  + radius;
  const dz = radius * DEAD_ZONE_PCT / 100 * 2;
  deadzone.style.width  = dz + 'px';
  deadzone.style.height = dz + 'px';
  deadzone.style.top    = ((r.height - dz) / 2) + 'px';
  deadzone.style.left   = ((r.width  - dz) / 2) + 'px';
}
sizeDeadZone();
window.addEventListener('resize', sizeDeadZone);

// ── Joystick math ─────────────────────────────────────────────────────────────
function pointerToJoy(pageX, pageY) {
  // Raw offset from center
  let dx = pageX - originX;
  let dy = pageY - originY;   // positive = down on screen

  // Clamp within circle
  const dist = Math.sqrt(dx*dx + dy*dy);
  if (dist > radius) {
    dx = dx / dist * radius;
    dy = dy / dist * radius;
  }

  // Convert to -100..100 normalised axes
  let normX =  dx / radius * 100;   // right positive
  let normY = -dy / radius * 100;   // up positive (forward)

  // Apply dead zone
  const deadR = DEAD_ZONE_PCT;
  const mag   = Math.sqrt(normX*normX + normY*normY);
  if (mag < deadR) {
    normX = 0; normY = 0;
  } else {
    // Re-scale so output starts from 0 right outside dead zone
    const scale = (mag - deadR) / (100 - deadR);
    normX = normX / mag * scale * 100;
    normY = normY / mag * scale * 100;
  }

  normX = Math.round(Math.max(-100, Math.min(100, normX)));
  normY = Math.round(Math.max(-100, Math.min(100, normY)));

  return { dx, dy, normX, normY };
}

// ── Update knob position ──────────────────────────────────────────────────────
function moveKnob(dx, dy) {
  // knob is already centered at 50%/50% via CSS; we translate from that point
  const hw = knob.offsetWidth  / 2;
  const hh = knob.offsetHeight / 2;
  knob.style.transform =
    'translate(calc(-50% + ' + Math.round(dx) + 'px), calc(-50% + ' + Math.round(dy) + 'px))';
}

// ── Status label ──────────────────────────────────────────────────────────────
function getLabel(jx, jy) {
  if (jx === 0 && jy === 0) return { text: 'STOP',     cls: 'stopped' };
  const ax = Math.abs(jx), ay = Math.abs(jy);
  if (ay > ax * 2) return { text: jy > 0 ? 'FORWARD'  : 'BACKWARD', cls: 'moving' };
  if (ax > ay * 2) return { text: jx > 0 ? 'RIGHT'    : 'LEFT',     cls: 'moving' };
  return { text: 'DRIVE', cls: 'moving' };
}

// ── Motor bars ────────────────────────────────────────────────────────────────
function setBar(fwdEl, revEl, speed) {
  // speed: -100..100
  if (speed >= 0) {
    fwdEl.style.width = speed / 2 + '%';  // half of track (center to right)
    revEl.style.width = '0%';
  } else {
    fwdEl.style.width = '0%';
    revEl.style.width = (-speed / 2) + '%';
  }
}

// ── Differential drive (mirrors ESP32 logic) ──────────────────────────────────
function mixSpeeds(jx, jy) {
  let L = jy + jx;
  let R = jy - jx;
  const peak = Math.max(Math.abs(L), Math.abs(R), 100);
  L = Math.round(L * 100 / peak);
  R = Math.round(R * 100 / peak);
  return { L, R };
}

// ── Network ───────────────────────────────────────────────────────────────────
function sendJoy(jx, jy) {
  if (inFlight) return;
  inFlight = true;
  const t0 = performance.now();
  fetch('/joy?x=' + jx + '&y=' + jy)
    .then(() => {
      pingEl.textContent = Math.round(performance.now() - t0) + 'ms';
    })
    .catch(() => { pingEl.textContent = 'ERR'; })
    .finally(() => { inFlight = false; });
}

function sendStop() {
  fetch('/stop').catch(() => {});
}

// ── Update all UI + send command ──────────────────────────────────────────────
function applyJoy(jx, jy) {
  lastJoyX = jx; lastJoyY = jy;

  const { L, R } = mixSpeeds(jx, jy);
  const spd = Math.round(Math.sqrt(jx*jx + jy*jy));

  // UI
  const lbl = getLabel(jx, jy);
  stateEl.textContent = lbl.text;
  stateEl.className   = lbl.cls;
  spdEl.textContent   = Math.min(100, spd);
  xEl.textContent     = jx;
  yEl.textContent     = jy;
  setBar(barLF, barLR, L);
  setBar(barRF, barRR, R);

  sendJoy(jx, jy);
}

function resetJoy() {
  active = false;
  clearInterval(sendTimer);
  sendTimer = null;
  knob.classList.remove('active');
  knob.style.transform = 'translate(-50%, -50%)';
  stateEl.textContent  = 'STOP';
  stateEl.className    = 'stopped';
  spdEl.textContent    = '0';
  xEl.textContent      = '0';
  yEl.textContent      = '0';
  setBar(barLF, barLR, 0);
  setBar(barRF, barRR, 0);
  sendStop();
}

// ── Pointer down (touch or mouse) ─────────────────────────────────────────────
function onDown(pageX, pageY) {
  // Re-measure in case of resize / scroll
  const r = base.getBoundingClientRect();
  radius  = r.width / 2;
  originX = r.left + radius;
  originY = r.top  + radius;

  active = true;
  knob.classList.add('active');

  onMove(pageX, pageY);

  // Repeat while held so failsafe keeps resetting
  sendTimer = setInterval(() => {
    if (active) sendJoy(lastJoyX, lastJoyY);
  }, SEND_INTERVAL);
}

function onMove(pageX, pageY) {
  if (!active) return;
  const { dx, dy, normX, normY } = pointerToJoy(pageX, pageY);
  moveKnob(dx, dy);
  applyJoy(normX, normY);
}

// ── Touch events ──────────────────────────────────────────────────────────────
base.addEventListener('touchstart', e => {
  e.preventDefault();
  const t = e.changedTouches[0];
  onDown(t.pageX, t.pageY);
}, { passive: false });

document.addEventListener('touchmove', e => {
  e.preventDefault();
  if (!active) return;
  const t = e.changedTouches[0];
  onMove(t.pageX, t.pageY);
}, { passive: false });

document.addEventListener('touchend',    () => resetJoy(), { passive: false });
document.addEventListener('touchcancel', () => resetJoy(), { passive: false });

// ── Mouse events ──────────────────────────────────────────────────────────────
base.addEventListener('mousedown', e => {
  onDown(e.pageX, e.pageY);
});

document.addEventListener('mousemove', e => {
  if (!active) return;
  onMove(e.pageX, e.pageY);
});

document.addEventListener('mouseup', () => resetJoy());
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP SERVER HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def parse_query_int(first_line, param, default=None):
    """
    Extract an integer query parameter from a request first line like:
      b'GET /joy?x=40&y=80 HTTP/1.1'
    Returns `default` if the parameter is missing or not a valid integer.
    """
    try:
        if isinstance(first_line, (bytes, bytearray)):
            first_line = first_line.decode()
        if "?" not in first_line:
            return default
        qs = first_line.split("?", 1)[1].split(" ")[0]
        for part in qs.split("&"):
            if part.startswith(param + "="):
                return int(part.split("=", 1)[1])
    except Exception:
        pass
    return default


def send_response(conn, status, content_type, body):
    """Send a minimal HTTP response."""
    if isinstance(body, str):
        body = body.encode()
    header = (
        "HTTP/1.1 {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(status, content_type, len(body))
    conn.sendall(header.encode() + body)


def handle_request(conn):
    """
    Read one HTTP request from `conn`, execute the corresponding command,
    and send a response.
    """
    global last_command_ms

    try:
        request = conn.recv(1024)
        if not request:
            return

        first_line = request.split(b"\r\n")[0]
        parts = first_line.split(b" ")
        path  = parts[1].decode() if len(parts) > 1 else "/"

        # Update failsafe timer on every command
        last_command_ms = time.ticks_ms()

        # ── Route ──────────────────────────────────────────────────────────

        if path == "/" or path == "/index.html":
            send_response(conn, "200 OK", "text/html", HTML)

        elif path.startswith("/joy"):
            jx = parse_query_int(first_line, "x", default=0)
            jy = parse_query_int(first_line, "y", default=0)
            jx = max(-100, min(100, jx))
            jy = max(-100, min(100, jy))
            drive_joystick(jx, jy)
            send_response(conn, "200 OK", "text/plain", "OK")
            # Only print non-zero commands to reduce serial spam
            if jx != 0 or jy != 0:
                print("JOY x={} y={}".format(jx, jy))

        elif path.startswith("/stop"):
            stop_all()
            send_response(conn, "200 OK", "text/plain", "OK")
            print("CMD: stop")

        else:
            send_response(conn, "404 Not Found", "text/plain", "Not found")

    except OSError:
        # Connection closed prematurely – normal on mobile browsers
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(("", 80))
server_socket.listen(3)
server_socket.settimeout(0.1)   # Non-blocking so failsafe can run

print("\nServer listening on port 80 – rover ready!")
print("=" * 50)

while True:
    # ── Failsafe ──────────────────────────────────────────────────────────
    elapsed = time.ticks_diff(time.ticks_ms(), last_command_ms)
    if elapsed > FAILSAFE_MS:
        stop_all()   # Safe to call repeatedly; just zeroes PWM duty

    # ── Accept connection ─────────────────────────────────────────────────
    try:
        conn, addr = server_socket.accept()
        conn.settimeout(2.0)
        handle_request(conn)
        conn.close()
    except OSError:
        pass   # Timeout on accept – loop back to failsafe check