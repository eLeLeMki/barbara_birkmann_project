import machine
import time

TOUCH_PIN = machine.TouchPad(machine.Pin(4))
THRESHOLD = 400
DEBOUNCE_COUNT = 5  # ile kolejnych zgodnych odczytów potrzeba

previous_state = None
pending_state = None
counter = 0

while True:
    is_touched = TOUCH_PIN.read() < THRESHOLD

    if is_touched == pending_state:
        counter += 1
    else:
        pending_state = is_touched
        counter = 1

    if counter >= DEBOUNCE_COUNT and pending_state != previous_state:
        previous_state = pending_state
        if previous_state:
            print("✓ Dotknięty")
        else:
            print("✗ Nie dotknięty")

    time.sleep(0.05)