import math
from machine import SoftI2C, Pin
from time import sleep_ms, ticks_ms, ticks_diff
from lib import tsl2591
from lib import ssd1306
from lib import encoder


# Hardware
i2c = SoftI2C(
    sda=Pin(11, pull=Pin.PULL_UP),
    scl=Pin(12, pull=Pin.PULL_UP),
    freq=100000
)
oled        = ssd1306.SSD1306_I2C(128, 64, i2c)
sensor      = tsl2591.TSL2591(i2c)
encoder_obj = encoder.RotaryEncoder(clk_pin=17, dt_pin=9, sw_pin=7)

# Sensor defaults 
sensor.gain             = tsl2591.GAIN_HIGH
sensor.integration_time = tsl2591.INTEGRATIONTIME_300MS

# Photographic constants 
CALIBRATION_K = 1.173
EV_OFFSET     = 0.0

ISO_VALUES = [50, 100, 200, 400, 800, 1600, 3200, 6400, 12800]

SHUTTERS = [
    (8,      "8s"),
    (4,      "4s"),
    (2,      "2s"),
    (1,      "1s"),
    (1/2,    "1/2"),
    (1/4,    "1/4"),
    (1/8,    "1/8"),
    (1/15,   "1/15"),
    (1/30,   "1/30"),
    (1/60,   "1/60"),
    (1/125,  "1/125"),
    (1/250,  "1/250"),
    (1/500,  "1/500"),
    (1/1000, "1/1000"),
    (1/2000, "1/2000"),
    (1/4000, "1/4000"),
]

APERTURES = [
    (1.0,  "f/1.0"),
    (1.4,  "f/1.4"),
    (2.0,  "f/2.0"),
    (2.8,  "f/2.8"),
    (4.0,  "f/4"),
    (5.6,  "f/5.6"),
    (8.0,  "f/8"),
    (11.0, "f/11"),
    (16.0, "f/16"),
    (22.0, "f/22"),
    (32.0, "f/32"),
]

DISPLAY_MODES = ["EV+EXPO", "A PRIORITY", "S PRIORITY", "GRAPH"]

# App state 
iso_idx      = 1      # ISO 100
aperture_idx = 3      # f/2.8
shutter_idx  = 10     # 1/125
mode_idx     = 0
menu         = None   

ev_val    = 0.0
lux_val   = 0.0
cct_val   = None
overflow  = False
ev_history = [0.0] * 128

def draw_boot():
    oled.fill(0)

    # Camera icon
    oled.rect(34, 10, 60, 30, 1)
    oled.ellipse(64, 25, 10, 10, 1)
    oled.rect(48, 5, 20, 8, 1)
    oled.fill_rect(68, 20, 3, 3, 1)

    # Center helper
    def center_text(text, y):
        x = (128 - len(text) * 8) // 2
        oled.text(text, x, y)

    # Text
    center_text("NanoLux", 42)

    oled.show()
    sleep_ms(1500)

    oled.fill(0)
    oled.show()
  
draw_boot()


#  EV calculation 
def lux_to_ev(lux, iso):
    if lux <= 0:
        return 0.0
    return math.log(lux * iso / (CALIBRATION_K * 100.0), 2)

def ev_to_lux(ev, iso):
    return (CALIBRATION_K * 100.0 * (2 ** ev)) / iso

def lux_to_cct(ch0, ch1):
    """
    Estimate Correlated Colour Temperature in Kelvin
    from TSL2591 raw channel counts.
    Uses the Lux/IR ratio method.
    Returns None if calculation is not possible.
    """
    if ch0 == 0 or ch1 == 0:
        return None
    ratio = ch1 / ch0
    if ratio <= 0.0:
        return None
    cct = int(2990 * (0.2082 / ratio) ** 1.3)
    return max(1000, min(cct, 12000))

# Exposure combinatorics 
def shutter_for_aperture(ev, aperture, iso):
    t = (aperture ** 2) / (2 ** ev)
    return t

def aperture_for_shutter(ev, shutter, iso):
    n = math.sqrt(shutter * (2 ** ev))
    return n

def nearest_shutter(t):
    best = 0
    best_diff = 999999
    for i, (s, _) in enumerate(SHUTTERS):
        diff = abs(math.log(max(s, 1e-9)) - math.log(max(t, 1e-9)))
        if diff < best_diff:
            best_diff = diff
            best = i
    return best

def nearest_aperture(n):
    best = 0
    best_diff = 999999
    for i, (a, _) in enumerate(APERTURES):
        diff = abs(a - n)
        if diff < best_diff:
            best_diff = diff
            best = i
    return best

def recommended_exposure(ev, iso):
    base_aperture = APERTURES[5][0]  # f/5.6
    t = shutter_for_aperture(ev, base_aperture, iso)
    si = nearest_shutter(t)
    actual_t = SHUTTERS[si][0]
    n = aperture_for_shutter(ev, actual_t, iso)
    ai = nearest_aperture(n)
    return ai, si

# EV scene label 
def ev_scene_label(ev):
    if ev < -2:  return "Moonless night"
    if ev < 0:   return "Night scene"
    if ev < 3:   return "Candlelight"
    if ev < 5:   return "Indoor dim"
    if ev < 7:   return "Indoor avg"
    if ev < 9:   return "Indoor bright"
    if ev < 11:  return "Overcast"
    if ev < 13:  return "Hazy sun"
    if ev < 15:  return "Full sun"
    if ev < 17:  return "Bright sun"
    return       "Extreme light"

  # OLED drawing 
def draw_ev_screen(ev, iso, overflow=False):
    oled.fill(0)
    if overflow:
        oled.text("!! OVERFLOW !!", 8, 4)
        oled.text("Reduce gain or", 4, 20)
        oled.text("integ. time", 10, 32)
        oled.show()
        return

    # EV — yellow band
    ev_str = "EV {:+.1f}".format(ev)
    x = max(0, (128 - len(ev_str) * 8) // 2)
    oled.text(ev_str, x, 0)

    # Scene label
    oled.text(ev_scene_label(ev), 0, 12)

    oled.hline(0, 22, 128, 1)

    # Suggested exposure 
    ai, si = recommended_exposure(ev, iso)
    oled.text("ISO {}".format(iso),     0, 25)
    oled.text(APERTURES[ai][1],         0, 36)
    oled.text(SHUTTERS[si][1],          0, 47)

    oled.hline(0, 56, 128, 1)
    oled.text("LX:{:.0f}".format(lux_val), 0, 57)
    if cct_val:
        oled.text("{}K".format(cct_val),  72, 57)
    oled.show()


def draw_a_priority(ev, iso):
    """A PRIORITY — locked aperture, shows matching shutter speed."""
    oled.fill(0)
    aperture = APERTURES[aperture_idx][0]
    t = shutter_for_aperture(ev, aperture, iso)
    si = nearest_shutter(t)

    # Header — yellow band
    oled.text("A PRIORITY", 20, 2)
    oled.hline(0, 13, 128, 1)

    # Settings row
    oled.text(APERTURES[aperture_idx][1], 0, 16)
    oled.text("ISO{}".format(iso),       72, 16)

    # Big shutter speed centred
    shutter_str = SHUTTERS[si][1]
    x = max(0, (128 - len(shutter_str) * 8) // 2)
    oled.text(shutter_str, x, 30)
    oled.text("shutter speed",           8, 43)

    # Status bar
    oled.hline(0, 54, 128, 1)
    oled.text("EV{:+.1f}".format(ev),   0, 56)
    if cct_val:
        oled.text("{}K".format(cct_val), 80, 56)
    oled.show()

def draw_s_priority(ev, iso):
    """S PRIORITY — locked shutter, shows matching aperture."""
    oled.fill(0)
    shutter = SHUTTERS[shutter_idx][0]
    n = aperture_for_shutter(ev, shutter, iso)
    ai = nearest_aperture(n)

    # Header — yellow band
    oled.text("S PRIORITY", 20, 2)
    oled.hline(0, 13, 128, 1)

    # Settings row
    oled.text(SHUTTERS[shutter_idx][1], 0, 16)
    oled.text("ISO{}".format(iso),     72, 16)

    # Big aperture centred
    ap_str = APERTURES[ai][1]
    x = max(0, (128 - len(ap_str) * 8) // 2)
    oled.text(ap_str, x, 30)
    oled.text("aperture",              36, 43)

    # Status bar
    oled.hline(0, 54, 128, 1)
    oled.text("EV{:+.1f}".format(ev),  0, 56)
    if cct_val:
        oled.text("{}K".format(cct_val), 80, 56)
    oled.show()

def draw_graph_screen(ev):
    oled.fill(0)
    oled.text("EV Graph", 0, 2)

    min_ev = min(ev_history)
    max_ev = max(ev_history)
    span   = max(max_ev - min_ev, 1.0)
    graph_h = 44

    for x, v in enumerate(ev_history):
        bar_h = int(((v - min_ev) / span) * graph_h)
        if bar_h > 0:
            oled.vline(x, 54 - bar_h, bar_h, 1)

    oled.hline(0, 55, 128, 1)
    oled.text("EV{:+.1f}".format(ev),          0, 57)
    oled.text("ISO{}".format(ISO_VALUES[iso_idx]), 72, 57)
    oled.show()

def draw_menu(title, items, selected):
    oled.fill(0)
    oled.text(title, 0, 0)
    oled.hline(0, 10, 128, 1)
    start = max(0, selected - 1)
    for i, item in enumerate(items[start: start + 3]):   # 3 items now, not 4
        y = 14 + i * 12
        actual_idx = start + i
        if actual_idx == selected:
            oled.fill_rect(0, y - 1, 128, 11, 1)
            oled.text("> " + str(item), 0, y, 0)
        else:
            oled.text("  " + str(item), 0, y)
    oled.hline(0, 53, 128, 1)
    oled.text("hold=back", 34, 56)   # reminder at bottom
    oled.show

# Main loop 
READ_INTERVAL_MS = 400
last_read_ms     = 0

while True:
    now = ticks_ms()
    iso = ISO_VALUES[iso_idx]

    # Short press: advance forward through menus
    if encoder_obj.get_pressed():
        if menu is None:
            menu = "ISO"
        elif menu == "ISO":
            menu = "APERTURE"
        elif menu == "APERTURE":
            menu = "SHUTTER"
        elif menu == "SHUTTER":
            menu = "MODE"
        elif menu == "MODE":
            menu = None

    # Long press: go back one menu step
    if encoder_obj.get_long_pressed():
        if menu == "ISO":
            menu = None
        elif menu == "APERTURE":
            menu = "ISO"
        elif menu == "SHUTTER":
            menu = "APERTURE"
        elif menu == "MODE":
            menu = "SHUTTER"

    # Encoder rotation
    delta = encoder_obj.get_delta()
    if delta != 0:
        if menu == "ISO":
            iso_idx = (iso_idx + delta) % len(ISO_VALUES)
        elif menu == "APERTURE":
            aperture_idx = (aperture_idx + delta) % len(APERTURES)
        elif menu == "SHUTTER":
            shutter_idx = (shutter_idx + delta) % len(SHUTTERS)
        elif menu == "MODE":
            mode_idx = (mode_idx + delta) % len(DISPLAY_MODES)

    # Sensor read every 400ms
    if ticks_diff(now, last_read_ms) >= READ_INTERVAL_MS:
        last_read_ms = now
        try:
            ch0, ch1 = sensor.raw_luminosity
            lux_val  = sensor.lux
            ev_val   = lux_to_ev(lux_val, iso)
            cct_val  = lux_to_cct(ch0, ch1)
            overflow = False
            ev_history.pop(0)
            ev_history.append(ev_val)
        except RuntimeError:
            overflow = True
        except Exception as e:
            print("Sensor error:", e)

    # Draw
    if menu == "ISO":
        draw_menu("Set ISO", ["ISO {}".format(v) for v in ISO_VALUES], iso_idx)
    elif menu == "APERTURE":
        draw_menu("Lock Aperture", [a[1] for a in APERTURES], aperture_idx)
    elif menu == "SHUTTER":
        draw_menu("Lock Shutter", [s[1] for s in SHUTTERS], shutter_idx)
    elif menu == "MODE":
        draw_menu("Display Mode", DISPLAY_MODES, mode_idx)
    else:
        mode = DISPLAY_MODES[mode_idx]
        if mode == "EV+EXPO":
            draw_ev_screen(ev_val, iso, overflow)
        elif mode == "A PRIORITY":
            draw_a_priority(ev_val, iso)
        elif mode == "S PRIORITY":
            draw_s_priority(ev_val, iso)
        elif mode == "GRAPH":
            draw_graph_screen(ev_val)

    sleep_ms(50)

