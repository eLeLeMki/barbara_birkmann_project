from machine import ADC, Pin
import time

# ── Konfiguracja ─────────────────────────────────────────────────────────────
# GPIO34 — dedykowany pin ADC-only na ESP32 (nie ma funkcji cyfrowej,
# idealny do analogowych czujników; nie nadaje się do PWM/I2C/SPI)
ADC_PIN      = 34
SAMPLE_RATE_MS = 100   # Odczyt co 100 ms

# ── Inicjalizacja ADC ─────────────────────────────────────────────────────────
adc = ADC(Pin(ADC_PIN))
adc.atten(ADC.ATTN_11DB)    # Zakres 0–3.3 V (pełna skala ESP32)
adc.width(ADC.WIDTH_12BIT)  # Rozdzielczość 12-bit → wartości 0–4095

print("Czujnik nacisku (Velostat) — start")
print(f"Pin: GPIO{ADC_PIN} | Próbkowanie: co {SAMPLE_RATE_MS} ms")
print("-" * 40)

# ── Pętla główna ──────────────────────────────────────────────────────────────
while True:
    raw   = adc.read()                        # Surowa wartość 0–4095
    volts = raw * 3.3 / 4095                  # Przeliczenie na napięcie [V]
    pct   = round(raw / 4095 * 100, 1)        # Procentowe wypełnienie skali

    print(f"ADC: {raw:4d} / 4095  |  {volts:.3f} V  |  {pct:5.1f}%")

    time.sleep_ms(SAMPLE_RATE_MS)