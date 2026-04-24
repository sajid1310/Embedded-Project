# Photography Lux Meter
### Arduino Nano ESP32 + TSL2591 + SSD1306 OLED + KY-040 Rotary Encoder

A handheld incident light meter for photographers, built on MicroPython. Displays EV (Exposure Value), suggested exposures, and supports aperture-priority and shutter-priority modes — just like a Sekonic or Gossen meter.

---

## Hardware

| Component | Model |
|---|---|
| Microcontroller | Arduino Nano ESP32 (ESP32-S3) |
| Light Sensor | TSL2591 (I2C) |
| Display | 128x64 OLED — SSD1306 (I2C, blue/yellow) |
| Input | Keyes KY-040 Rotary Encoder |

---

## File Structure

```
/ (device root)
├── boot.py              ← runs first on power up
├── main.py              ← main application
└── lib/
    ├── __init__.py      ← makes lib a Python package (can be empty)
    ├── tsl2591.py       ← TSL2591 light sensor driver
    ├── ssd1306.py       ← SSD1306 OLED display driver
    └── encoder.py       ← KY-040 rotary encoder driver
```

> `boot.py` and `main.py` **must** be at the root of the device, not inside any subfolder.

---

## Wiring

### I2C Bus (shared by TSL2591 and OLED)

| Signal | ESP32 GPIO |
|---|---|
| SDA | GPIO 11 |
| SCL | GPIO 12 |

Both the TSL2591 (address `0x29`) and the SSD1306 OLED (address `0x3C`) share the same I2C bus — no conflict.

### KY-040 Rotary Encoder

| KY-040 Pin | ESP32 GPIO |
|---|---|
| CLK | GPIO 17 |
| DT | GPIO 18 |
| SW | GPIO 9 |
| + (VCC) | 3.3V |
| GND | GND |

> The `+` pin on the KY-040 **must** be connected to 3.3V to power the onboard pull-up resistors. Without it the encoder will not work reliably.

### Power

The device runs from any 5V USB source (power bank, phone charger, USB wall adapter). No laptop required once code is loaded.

---

## Display Modes

Cycle through modes using the encoder button and rotation.

### EV + EXPOSURE (default)
- Large EV number centred on screen
- Scene label (e.g. *Full sun*, *Overcast*, *Indoor dim*)
- Suggested ISO / aperture / shutter combination
- Live lux reading in status bar

### APERTURE LOCK
- You set your aperture with the encoder
- Meter shows the correct matching shutter speed
- EV and lux shown in status bar

### SHUTTER LOCK
- You set your shutter speed with the encoder
- Meter shows the correct matching aperture
- EV and lux shown in status bar

### EV GRAPH
- Rolling bar graph of EV history across full screen width
- Current EV and ISO shown at bottom
- Useful for tracking changing or mixed light conditions

---

## Encoder Controls

| Action | Result |
|---|---|
| **Press** | Advance to next menu (ISO → Aperture → Shutter → Mode → back to live) |
| **Rotate** | Scroll through options in current menu |

### Menu Flow
```
Live View → [press] → Set ISO → [press] → Lock Aperture → [press] → Lock Shutter → [press] → Display Mode → [press] → Live View
```

---

## Settings

### ISO Values
50, 100, 200, 400, 800, 1600, 3200, 6400, 12800

### Aperture Values (f-stops)
f/1.0, f/1.4, f/2.0, f/2.8, f/4, f/5.6, f/8, f/11, f/16, f/22, f/32

### Shutter Speeds
8s, 4s, 2s, 1s, 1/2, 1/4, 1/8, 1/15, 1/30, 1/60, 1/125, 1/250, 1/500, 1/1000, 1/2000, 1/4000

---

## EV Scene Reference

| EV Range | Scene |
|---|---|
| Below -2 | Moonless night |
| -2 to 0 | Night scene |
| 0 to 3 | Candlelight |
| 3 to 5 | Indoor dim |
| 5 to 7 | Indoor average |
| 7 to 9 | Indoor bright |
| 9 to 11 | Overcast |
| 11 to 13 | Hazy sun |
| 13 to 15 | Full sun |
| 15 to 17 | Bright sun |
| Above 17 | Extreme light |

---

## Overflow Warning

If the TSL2591 sensor saturates (too much light for the current gain/integration settings), the display shows:

```
!! OVERFLOW !!
Reduce gain or
integration time
```

This is handled automatically — enter the sensor settings and reduce gain or integration time.

### TSL2591 Gain Settings
| Setting | Multiplier |
|---|---|
| LOW | 1x |
| MED | 25x |
| HIGH | 428x |
| MAX | 9876x |

### TSL2591 Integration Times
100ms, 200ms, 300ms, 400ms, 500ms, 600ms

---

## EV Calculation

The meter uses the standard incident-light formula:

```
EV = log2( lux × ISO / (K × 100) )
```

Where **K = 12.5** — the calibration constant used by most modern cameras (Canon, Nikon, Sony). This matches the standard used by Sekonic and Gossen meters.

---

## Installation

### Requirements
- MicroPython v1.19 or later installed on the ESP32

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `ImportError: no module named 'ssd1306'` | File in wrong folder | Move `ssd1306.py` to `lib/` folder |
| `NameError: SSD1306_I2C not defined` | Missing import line | Check top of `main.py` for `from lib import ssd1306` |
| Encoder rotation not working | CLK/DT swapped | Swap GPIO 17 and 18, or swap wires |
| Encoder jumps and bounces | Debounce too low | Increase `_ROT_DEBOUNCE_MS` in `encoder.py` to 80 or 100 |
| Button press registers as rotation | Wiring issue | Check all 5 KY-040 wires, especially GND and `+` |
| Sensor not found | Wrong I2C pins or address | Run `i2c.scan()` in REPL — should return `[0x29, 0x3C]` |
| Display blank | OLED not powered or wrong address | Check SDA/SCL wiring and that OLED is at `0x3C` |
| Won't start without laptop | `main.py` not at root | Ensure `main.py` is at `/` not inside `/lib/` |

---

## Dependencies

All drivers are included in the `lib/` folder — no internet connection or package manager required on the device.

| File | Source |
|---|---|
| `tsl2591.py` | Custom MicroPython driver |
| `ssd1306.py` | [MicroPython official library](https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/display/ssd1306/ssd1306.py) |
| `encoder.py` | Custom debounced KY-040 driver |

---

## License

Open source. Free to use, modify, and distribute for personal and educational projects.
