# =============================================================================
#  rover_wifi_control.py  –  ESP32 MicroPython Wi-Fi Rover Controller
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
#     The control page will load – tap and hold buttons to drive!
#
# =============================================================================

import network
import socket
import time
from machine import Pin, PWM

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION – change these if needed
# ─────────────────────────────────────────────────────────────────────────────

AP_SSID = "ESP32-Rover"  # Wi-Fi network name your phone will see
AP_PASSWORD = "rover1234"  # Must be 8+ characters for WPA2; set "" for open network
AP_IP = "192.168.4.1"  # The IP you open in the browser (this is the default)

PWM_FREQ = 1000  # Hz – motor PWM frequency
FAILSAFE_MS = 500  # Stop motors if no command received for this many ms

# ─────────────────────────────────────────────────────────────────────────────
#  MOTOR SETUP
#  Each motor has:
#    "dir" – direction pin (HIGH = one way, LOW = other way)
#    "pwm" – PWM pin that controls speed (duty_u16: 0 = stop, 65535 = full speed)
# ─────────────────────────────────────────────────────────────────────────────

motors = [
    {
        "name": "Motor 1 (front-left)",
        "dir": Pin(5, Pin.OUT),
        "pwm": PWM(Pin(17), freq=PWM_FREQ),
    },
    {
        "name": "Motor 2 (front-right)",
        "dir": Pin(4, Pin.OUT),
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
    m["pwm"].duty_u16(0)  # Zero duty cycle = motor stopped
    m["dir"].value(0)  # Direction pin low

print("Motors initialised and stopped.")

# Global speed (0–100 %) – updated by the /speed endpoint
current_speed_pct = 60  # Default 60 % – a safe, controllable starting speed

# Timestamp of the last command received (used by the failsafe)
last_command_ms = time.ticks_ms()


# ─────────────────────────────────────────────────────────────────────────────
#  MOTOR CONTROL FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def speed_to_duty(speed_pct):
    """Convert a 0-100 % speed value to a 16-bit duty cycle (0–65535)."""
    speed_pct = max(0, min(100, speed_pct))  # Clamp to valid range
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


def forward(speed_pct=None):
    """
    Drive all four motors in the forward direction.
    Uses current_speed_pct if no speed is given.
    """
    spd = speed_pct if speed_pct is not None else current_speed_pct
    # Left-side motors and right-side motors spin the SAME direction
    # to propel the rover forward.
    # Adjust True/False per motor if your rover moves the wrong way.
    set_motor(motors[0], True, spd)  # front-left  → forward
    set_motor(motors[1], True, spd)  # front-right → forward
    set_motor(motors[2], True, spd)  # rear-left   → forward
    set_motor(motors[3], True, spd)  # rear-right  → forward


def backward(speed_pct=None):
    """Drive all four motors in the reverse direction."""
    spd = speed_pct if speed_pct is not None else current_speed_pct
    set_motor(motors[0], False, spd)
    set_motor(motors[1], False, spd)
    set_motor(motors[2], False, spd)
    set_motor(motors[3], False, spd)


def left(speed_pct=None):
    """
    Turn left by spinning left-side motors backward and right-side forward.
    This is a 'tank turn' (spin in place) – reduce speed if you prefer a gentle arc.
    """
    spd = speed_pct if speed_pct is not None else current_speed_pct
    set_motor(motors[0], False, spd)  # front-left  → backward
    set_motor(motors[1], True, spd)  # front-right → forward
    set_motor(motors[2], False, spd)  # rear-left   → backward
    set_motor(motors[3], True, spd)  # rear-right  → forward


def right(speed_pct=None):
    """Turn right – mirror of left()."""
    spd = speed_pct if speed_pct is not None else current_speed_pct
    set_motor(motors[0], True, spd)  # front-left  → forward
    set_motor(motors[1], False, spd)  # front-right → backward
    set_motor(motors[2], True, spd)  # rear-left   → forward
    set_motor(motors[3], False, spd)  # rear-right  → backward


# ─────────────────────────────────────────────────────────────────────────────
#  WI-FI ACCESS POINT SETUP
# ─────────────────────────────────────────────────────────────────────────────

print("Starting Wi-Fi access point...")

ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=3)  # authmode 3 = WPA2

# Wait until the AP is actually up
while not ap.active():
    time.sleep(0.1)

print(f"Access point active!")
print(f"  SSID    : {AP_SSID}")
print(f"  Password: {AP_PASSWORD}")
print(f"  IP      : {ap.ifconfig()[0]}")
print(f"  Open    : http://{ap.ifconfig()[0]} in your phone browser")

# ─────────────────────────────────────────────────────────────────────────────
#  HTML PAGE
#  The entire web interface is stored here as a Python string.
#  It is served once when the browser loads '/', then all commands
#  are sent as tiny GET requests (/forward, /stop, /speed?v=70, etc.)
#  so there is no page reload needed while driving.
# ─────────────────────────────────────────────────────────────────────────────

HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>ESP32 Rover</title>
<style>
  /* ── Reset & base ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  /* ── Design: industrial/utilitarian dark theme ── */
  :root {
    --bg:       #0d0d0d;
    --surface:  #1a1a1a;
    --border:   #2e2e2e;
    --accent:   #e8ff00;      /* electric yellow – high-vis, rover-like */
    --danger:   #ff3b30;
    --text:     #f0f0f0;
    --muted:    #666;
    --btn-h:    110px;
    --radius:   6px;
    --font:     'Courier New', Courier, monospace;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 16px;
    gap: 16px;
    /* prevent text selection while tapping buttons */
    -webkit-user-select: none;
    user-select: none;
    touch-action: manipulation;
  }

  /* ── Header ── */
  header {
    width: 100%;
    max-width: 480px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px;
  }
  header h1 { font-size: 1rem; letter-spacing: 0.2em; color: var(--accent); text-transform: uppercase; }
  #status {
    font-size: 0.7rem;
    color: var(--muted);
    text-align: right;
    line-height: 1.4;
  }
  #status span { display: block; }
  #status .live { color: #4cff91; }

  /* ── D-pad grid ── */
  .dpad {
    width: 100%;
    max-width: 360px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(3, var(--btn-h));
    gap: 8px;
  }

  /* ── Buttons ── */
  .btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--font);
    font-size: 1.8rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 4px;
    transition: background 0.08s, transform 0.08s, border-color 0.08s;
    /* disable native tap highlight on mobile */
    -webkit-tap-highlight-color: transparent;
  }
  .btn small { font-size: 0.55rem; letter-spacing: 0.15em; color: var(--muted); text-transform: uppercase; }

  /* Pressed state – applied by JS */
  .btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #000;
    transform: scale(0.96);
  }
  .btn.active small { color: #333; }

  /* Stop button */
  .btn-stop {
    background: #1f0000;
    border-color: var(--danger);
    color: var(--danger);
  }
  .btn-stop.active, .btn-stop:active {
    background: var(--danger);
    color: #fff;
  }

  /* Grid placement */
  .btn-fwd   { grid-column: 2; grid-row: 1; }
  .btn-left  { grid-column: 1; grid-row: 2; }
  .btn-stop  { grid-column: 2; grid-row: 2; }
  .btn-right { grid-column: 3; grid-row: 2; }
  .btn-bwd   { grid-column: 2; grid-row: 3; }

  /* ── Speed control ── */
  .speed-panel {
    width: 100%;
    max-width: 360px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 18px;
  }
  .speed-panel label {
    display: flex;
    justify-content: space-between;
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .speed-panel label span { color: var(--accent); font-size: 0.85rem; }

  /* Custom range slider */
  input[type=range] {
    -webkit-appearance: none;
    width: 100%;
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    outline: none;
  }
  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 3px solid var(--bg);
    box-shadow: 0 0 8px rgba(232,255,0,0.4);
  }
  input[type=range]::-moz-range-thumb {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 3px solid var(--bg);
  }

  /* Speed step buttons */
  .speed-steps {
    display: flex;
    justify-content: space-between;
    margin-top: 10px;
    gap: 6px;
  }
  .step-btn {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--muted);
    font-family: var(--font);
    font-size: 0.7rem;
    padding: 6px 0;
    cursor: pointer;
    text-align: center;
    letter-spacing: 0.1em;
    transition: background 0.1s, color 0.1s, border-color 0.1s;
  }
  .step-btn.sel {
    background: var(--accent);
    border-color: var(--accent);
    color: #000;
  }

  /* ── Footer ── */
  footer {
    font-size: 0.6rem;
    color: var(--muted);
    letter-spacing: 0.1em;
    text-align: center;
    line-height: 1.8;
  }
</style>
</head>
<body>

<header>
  <h1>&#x25B6; ESP32 ROVER</h1>
  <div id="status">
    <span id="cmd-line">STANDBY</span>
    <span id="ping-line" class="muted">PING: --</span>
  </div>
</header>

<!-- D-pad -->
<div class="dpad">
  <button class="btn btn-fwd"   id="btn-fwd"  >&#x2191;<small>FWD</small></button>
  <button class="btn btn-left"  id="btn-left" >&#x2190;<small>LEFT</small></button>
  <button class="btn btn-stop"  id="btn-stop" >&#x25A0;<small>STOP</small></button>
  <button class="btn btn-right" id="btn-right">&#x2192;<small>RIGHT</small></button>
  <button class="btn btn-bwd"   id="btn-bwd"  >&#x2193;<small>BWD</small></button>
</div>

<!-- Speed control -->
<div class="speed-panel">
  <label>SPEED <span id="spd-val">60%</span></label>
  <input type="range" id="speed-slider" min="10" max="100" value="60" step="5">
  <div class="speed-steps">
    <div class="step-btn" data-v="25">LOW</div>
    <div class="step-btn sel" data-v="60">MED</div>
    <div class="step-btn" data-v="85">HIGH</div>
    <div class="step-btn" data-v="100">MAX</div>
  </div>
</div>

<footer>
  HOLD BUTTON TO MOVE &nbsp;|&nbsp; RELEASE TO STOP<br>
  ESP32-ROVER &nbsp;/&nbsp; MICROPYTHON
</footer>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let currentSpeed = 60;
let activeButton = null;   // which direction button is held
let repeatTimer  = null;   // interval that re-sends the command while held
let pingStart    = 0;

// ── Helpers ────────────────────────────────────────────────────────────────
function cmd(endpoint) {
  // Fire-and-forget GET request – no page reload
  pingStart = performance.now();
  fetch(endpoint)
    .then(r => {
      const ms = Math.round(performance.now() - pingStart);
      document.getElementById('ping-line').textContent = 'PING: ' + ms + 'ms';
      document.getElementById('ping-line').className = ms < 200 ? 'live' : 'muted';
    })
    .catch(() => {
      document.getElementById('ping-line').textContent = 'PING: ERR';
      document.getElementById('ping-line').className = 'muted';
    });
}

function setStatus(text) {
  document.getElementById('cmd-line').textContent = text;
}

// ── Speed ──────────────────────────────────────────────────────────────────
const slider    = document.getElementById('speed-slider');
const spdLabel  = document.getElementById('spd-val');
const stepBtns  = document.querySelectorAll('.step-btn');

function applySpeed(v) {
  currentSpeed = v;
  slider.value = v;
  spdLabel.textContent = v + '%';
  // Highlight matching preset button (if any)
  stepBtns.forEach(b => {
    b.classList.toggle('sel', parseInt(b.dataset.v) === v);
  });
  cmd('/speed?v=' + v);
}

slider.addEventListener('input', () => applySpeed(parseInt(slider.value)));
slider.addEventListener('change', () => applySpeed(parseInt(slider.value)));

stepBtns.forEach(btn => {
  btn.addEventListener('click', () => applySpeed(parseInt(btn.dataset.v)));
});

// ── D-pad button logic ─────────────────────────────────────────────────────
//
//  We send the command immediately on press, then repeat every 250 ms while
//  held so the ESP32 failsafe timer keeps getting reset (it stops motors
//  after 500 ms of silence).  On release we send /stop immediately.
//
const btnMap = {
  'btn-fwd':   { endpoint: '/forward',  label: 'FWD'   },
  'btn-bwd':   { endpoint: '/backward', label: 'BWD'   },
  'btn-left':  { endpoint: '/left',     label: 'LEFT'  },
  'btn-right': { endpoint: '/right',    label: 'RIGHT' },
  'btn-stop':  { endpoint: '/stop',     label: 'STOP'  },
};

function pressButton(id) {
  if (activeButton === id) return;    // already held
  releaseButton();                    // release any previous button
  activeButton = id;
  const info = btnMap[id];
  document.getElementById(id).classList.add('active');
  setStatus(info.label);
  cmd(info.endpoint);
  if (id !== 'btn-stop') {
    // Keep sending while held so the failsafe timer keeps resetting
    repeatTimer = setInterval(() => cmd(info.endpoint), 250);
  }
}

function releaseButton() {
  if (!activeButton) return;
  const prev = activeButton;
  activeButton = null;
  clearInterval(repeatTimer);
  repeatTimer = null;
  document.getElementById(prev).classList.remove('active');
  if (prev !== 'btn-stop') {
    cmd('/stop');
    setStatus('STOP');
  }
}

Object.keys(btnMap).forEach(id => {
  const el = document.getElementById(id);

  // Touch events (mobile)
  el.addEventListener('touchstart', e => { e.preventDefault(); pressButton(id); }, { passive: false });
  el.addEventListener('touchend',   e => { e.preventDefault(); if (id !== 'btn-stop') releaseButton(); }, { passive: false });
  el.addEventListener('touchcancel',e => { e.preventDefault(); releaseButton(); }, { passive: false });

  // Mouse events (desktop / Thonny browser preview)
  el.addEventListener('mousedown', () => pressButton(id));
  el.addEventListener('mouseup',   () => { if (id !== 'btn-stop') releaseButton(); });
  el.addEventListener('mouseleave',() => { if (activeButton === id && id !== 'btn-stop') releaseButton(); });
});

// Safety: release if pointer leaves the window entirely
window.addEventListener('mouseup',    releaseButton);
window.addEventListener('touchend',   releaseButton);
window.addEventListener('touchcancel',releaseButton);
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP SERVER
#  MicroPython has no web framework, so we implement a tiny one ourselves.
#  The server handles one request at a time (single-threaded) which is
#  perfectly fine for a rover controller.
# ─────────────────────────────────────────────────────────────────────────────

def parse_query_int(request_line, param, default=None):
    """
    Extract an integer query parameter from a request line like:
      b'GET /speed?v=75 HTTP/1.1'
    Returns `default` if the parameter is missing or not a valid integer.
    """
    try:
        # Decode bytes to string if needed
        if isinstance(request_line, (bytes, bytearray)):
            request_line = request_line.decode()
        # Find the query string portion
        if "?" not in request_line:
            return default
        qs = request_line.split("?", 1)[1].split(" ")[0]  # strip HTTP version
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
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    conn.sendall(header.encode() + body)


def handle_request(conn):
    """
    Read one HTTP request from `conn`, execute the corresponding command,
    and send a response.
    """
    global current_speed_pct, last_command_ms

    try:
        # Read the first line of the HTTP request (e.g. "GET /forward HTTP/1.1")
        request = conn.recv(1024)
        if not request:
            return

        first_line = request.split(b"\r\n")[0]  # e.g. b'GET /forward HTTP/1.1'
        path = first_line.split(b" ")[1].decode() if len(first_line.split(b" ")) > 1 else "/"

        # Update the failsafe timer on every command
        last_command_ms = time.ticks_ms()

        # ── Route the request ──────────────────────────────────────────────
        if path == "/" or path == "/index.html":
            # Serve the main HTML page
            send_response(conn, "200 OK", "text/html", HTML)

        elif path.startswith("/forward"):
            forward()
            send_response(conn, "200 OK", "text/plain", "OK")
            print("CMD: forward")

        elif path.startswith("/backward"):
            backward()
            send_response(conn, "200 OK", "text/plain", "OK")
            print("CMD: backward")

        elif path.startswith("/left"):
            left()
            send_response(conn, "200 OK", "text/plain", "OK")
            print("CMD: left")

        elif path.startswith("/right"):
            right()
            send_response(conn, "200 OK", "text/plain", "OK")
            print("CMD: right")

        elif path.startswith("/stop"):
            stop_all()
            send_response(conn, "200 OK", "text/plain", "OK")
            print("CMD: stop")

        elif path.startswith("/speed"):
            v = parse_query_int(first_line, "v", default=current_speed_pct)
            current_speed_pct = max(0, min(100, v))
            send_response(conn, "200 OK", "text/plain", f"speed={current_speed_pct}")
            print(f"CMD: speed={current_speed_pct}%")

        else:
            # Unknown path – return 404
            send_response(conn, "404 Not Found", "text/plain", "Not found")

    except OSError:
        # Connection was closed prematurely – this is normal on mobile browsers
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

# Create a TCP socket and bind to port 80 (standard HTTP)
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(("", 80))
server_socket.listen(3)  # Allow up to 3 queued connections
server_socket.settimeout(0.1)  # Non-blocking accept so we can run the failsafe

print("\nServer listening on port 80 – rover ready!")
print("=" * 50)

while True:
    # ── Failsafe check ────────────────────────────────────────────────────
    # If no command has been received recently, stop all motors.
    # This protects against the rover running away if Wi-Fi drops.
    elapsed = time.ticks_diff(time.ticks_ms(), last_command_ms)
    if elapsed > FAILSAFE_MS:
        stop_all()  # Safe to call repeatedly – it just sets duty to 0 each time

    # ── Accept incoming connection ─────────────────────────────────────────
    try:
        conn, addr = server_socket.accept()
        conn.settimeout(2.0)  # Don't hang waiting for a slow client
        handle_request(conn)
        conn.close()
    except OSError:
        # Timeout on accept – that's fine, loop back and check failsafe again
        pass