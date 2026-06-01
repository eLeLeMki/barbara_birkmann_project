from machine import Pin, PWM

# --- Motor Configuration ---
MOTOR1_DIR_PIN = 4
MOTOR1_PWM_PIN = 16

MOTOR2_DIR_PIN = 5
MOTOR2_PWM_PIN = 17

PWM_FREQ = 1000  # 1 kHz PWM frequency
MAX_DUTY = 1023  # ESP32 MicroPython duty range: 0–1023


class Motor:
    def __init__(self, dir_pin, pwm_pin, freq=PWM_FREQ):
        self.dir = Pin(dir_pin, Pin.OUT)
        self.pwm = PWM(Pin(pwm_pin), freq=freq)
        self.set(0)  # Start stopped

    def set(self, power):
        """
        Set motor speed and direction.
        power: float from -1.0 (full reverse) to 1.0 (full forward)
               0.0 = stop
        """
        power = max(-1.0, min(1.0, power))  # Clamp to [-1, 1]

        if power >= 0:
            self.dir.value(1)  # Forward
        else:
            self.dir.value(0)  # Reverse
            power = -power  # Use absolute value for duty

        duty = int(power * MAX_DUTY)
        self.pwm.duty(duty)

    def stop(self):
        self.set(0)


# --- Initialise motors ---
motor1 = Motor(MOTOR1_DIR_PIN, MOTOR1_PWM_PIN)
motor2 = Motor(MOTOR2_DIR_PIN, MOTOR2_PWM_PIN)

# --- Start both motors at 50% power (forward) ---
motor1.set(0.5)
motor2.set(0.5)

print("Motors running at 50% power.")
print("Call motor1.set(power) or motor2.set(power) to change speed.")
print("Use motor1.stop() / motor2.stop() to halt.")
