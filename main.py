import math
from machine import SoftI2C, Pin
from time import sleep_ms, ticks_ms, ticks_diff
from lib import tsl2591
from lib import ssd1306
from lib import encoder

# ── Hardware ──────────────────────────────────────────────────────────────────
i2c = SoftI2C(
    sda=Pin(11, pull=Pin.PULL_UP),
    scl=Pin(12, pull=Pin.PULL_UP),
    freq=100000
)
oled    = ssd1306.SSD1306_I2C(128, 64, i2c)
sensor  = tsl2591.TSL2591(i2c)
encoder_obj = encoder.RotaryEncoder(clk_pin=17, dt_pin=9, sw_pin=7)

# ── Sensor defaults ───────────────────────────────────────────────────────────
sensor.gain             = tsl2591.GAIN_LOW
sensor.integration_time = tsl2591.INTEGRATIONTIME_100MS

# ── Photographic constants ────────────────────────────────────────────────────
CALIBRATION_K = 12.5   # incident-light meter constant (12.5 = most cameras)

ISO_VALUES = [50, 100, 200, 400, 800, 1600, 3200, 6400, 12800]

# Standard shutter speeds (stored as fractions, displayed as strings)
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

# Standard apertures (f-stops)
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

DISPLAY_MODES = ["EV+EXPO", "SHUTTER", "APERTURE", "GRAPH"]
#  EV+EXPO   → big EV number + one recommended exposure combo
#  SHUTTER   → locked aperture, shows matching shutter speed
#  APERTURE  → locked shutter, shows matching aperture
#  GRAPH     → EV history bar graph

# ── App state ─────────────────────────────────────────────────────────────────
iso_idx      = 1      # ISO 100
aperture_idx = 3      # f/2.8
shutter_idx  = 10     # 1/125
mode_idx     = 0
menu         = None   # None | "ISO" | "APERTURE" | "SHUTTER" | "MODE"

ev_val       = 0.0
lux_val      = 0.0
overflow     = False
ev_history   = [0.0] * 128

# ── EV calculation ────────────────────────────────────────────────────────────
def lux_to_ev(lux, iso):
    if lux <= 0:
        return 0.0
    return math.log(lux * iso / (CALIBRATION_K * 100.0), 2)
    # Note: lux * ISO / (K * 100) normalises to ISO 100 base

def ev_to_lux(ev, iso):
    return (CALIBRATION_K * 100.0 * (2 ** ev)) / iso

# ── Exposure combinatorics ────────────────────────────────────────────────────
def shutter_for_aperture(ev, aperture, iso):
    """Given EV and aperture, return ideal shutter speed in seconds."""
    # EV = log2(N² / t)  where N=aperture, t=shutter (at box ISO 100)
    # Adjusted for actual ISO: EV_adj = EV - log2(iso/100)
    ev_adj = ev - math.log(iso / 100.0, 2)
    t = (aperture ** 2) / (2 ** ev_adj)
    return t

def aperture_for_shutter(ev, shutter, iso):
    """Given EV and shutter speed, return ideal aperture (N)."""
    ev_adj = ev - math.log(iso / 100.0, 2)
    n = math.sqrt(shutter * (2 ** ev_adj))
    return n

def nearest_shutter(t):
    """Find nearest standard shutter speed."""
    best = 0
    best_diff = 999999
    for i, (s, _) in enumerate(SHUTTERS):
        diff = abs(math.log(max(s, 1e-9)) - math.log(max(t, 1e-9)))
        if diff < best_diff:
            best_diff = diff
            best = i
    return best

def nearest_aperture(n):
    """Find nearest standard aperture."""
    best = 0
    best_diff = 999999
    for i, (a, _) in enumerate(APERTURES):
        diff = abs(a - n)
        if diff < best_diff:
            best_diff = diff
            best = i
    return best

def recommended_exposure(ev, iso):
    """
    Return a balanced exposure suggestion:
    tries to pick a mid-range aperture + appropriate shutter.
    """
    # Start from f/5.6 as a neutral aperture
    base_aperture = APERTURES[7][0]  # f/5.6
    t = shutter_for_aperture(ev, base_aperture, iso)
    si = nearest_shutter(t)
    # Use actual nearest shutter to get corrected aperture
    actual_t = SHUTTERS[si][0]
    n = aperture_for_shutter(ev, actual_t, iso)
    ai = nearest_aperture(n)
    return ai, si

# ── OLED drawing ──────────────────────────────────────────────────────────────
def draw_ev_screen(ev, iso, overflow=False):
    oled.fill(0)
    if overflow:
        oled.text("!! OVERFLOW !!", 8, 4)
        oled.text("Reduce gain or", 4, 20)
        oled.text("integration time", 0, 32)
        oled.hline(0, 46, 128, 1)
        oled.text("ISO{}".format(ISO_VALUES[iso_idx]), 0, 53)
        oled.show()
        return

    # Large EV value centred
    ev_str  = "EV {:+.1f}".format(ev)
    x = max(0, (128 - len(ev_str) * 8) // 2)
    oled.text(ev_str, x, 4)

    # EV scene reference
    oled.text(ev_scene_label(ev), 0, 18)

    # Suggested exposure
    ai, si = recommended_exposure(ev, iso)
    oled.hline(0, 30, 128, 1)
    oled.text("ISO{}".format(iso),          0, 34)
    oled.text(APERTURES[ai][1],            56, 34)
    oled.text(SHUTTERS[si][1],              0, 46)
    oled.text("(suggested)",               56, 46)

    # Bottom status
    oled.hline(0, 56, 128, 1)
    oled.text("LX:{:.0f}".format(lux_val), 0, 57)
    oled.show()

def draw_shutter_priority(ev, iso):
    """Locked aperture → show shutter speed."""
    oled.fill(0)
    aperture = APERTURES[aperture_idx][0]
    t = shutter_for_aperture(ev, aperture, iso)
    si = nearest_shutter(t)

    oled.text("APERTURE LOCK", 0, 0)
    oled.hline(0, 10, 128, 1)
    oled.text(APERTURES[aperture_idx][1], 0, 14)
    oled.text("ISO{}".format(iso),       72, 14)

    shutter_str = SHUTTERS[si][1]
    x = max(0, (128 - len(shutter_str) * 8) // 2)
    oled.text(shutter_str, x, 30)
    oled.text("shutter", 40, 44)

    oled.hline(0, 54, 128, 1)
    oled.text("EV{:+.1f}".format(ev), 0, 57)
    oled.text("LX:{:.0f}".format(lux_val), 64, 57)
    oled.show()

def draw_aperture_priority(ev, iso):
    """Locked shutter → show aperture."""
    oled.fill(0)
    shutter = SHUTTERS[shutter_idx][0]
    n = aperture_for_shutter(ev, shutter, iso)
    ai = nearest_aperture(n)

    oled.text("SHUTTER LOCK", 0, 0)
    oled.hline(0, 10, 128, 1)
    oled.text(SHUTTERS[shutter_idx][1], 0, 14)
    oled.text("ISO{}".format(iso),      72, 14)

    ap_str = APERTURES[ai][1]
    x = max(0, (128 - len(ap_str) * 8) // 2)
    oled.text(ap_str, x, 30)
    oled.text("aperture", 36, 44)

    oled.hline(0, 54, 128, 1)
    oled.text("EV{:+.1f}".format(ev), 0, 57)
    oled.text("LX:{:.0f}".format(lux_val), 64, 57)
    oled.show()

def draw_graph_screen(ev):
    oled.fill(0)
    oled.text("EV Graph", 0, 0)

    min_ev = min(ev_history)
    max_ev = max(ev_history)
    span   = max(max_ev - min_ev, 1.0)
    graph_h = 44

    for x, v in enumerate(ev_history):
        bar_h = int(((v - min_ev) / span) * graph_h)
        if bar_h > 0:
            oled.vline(x, 54 - bar_h, bar_h, 1)

    oled.hline(0, 55, 128, 1)
    oled.text("EV{:+.1f}".format(ev), 0, 57)
    oled.text("ISO{}".format(ISO_VALUES[iso_idx]), 72, 57)
    oled.show()

def draw_menu(title, items, selected):
    oled.fill(0)
    oled.text(title, 0, 0)
    oled.hline(0, 10, 128, 1)
    start = max(0, selected - 1)
    for i, item in enumerate(items[start: start + 4]):
        y = 14 + i * 12
        actual_idx = start + i
        if actual_idx == selected:
            oled.fill_rect(0, y - 1, 128, 11, 1)
            oled.text("> " + str(item), 0, y, 0)
        else:
            oled.text("  " + str(item), 0, y)
    oled.show()

def ev_scene_label(ev):
    """Human-readable scene description for a given EV."""
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

# ── Main loop ─────────────────────────────────────────────────────────────────
READ_INTERVAL_MS = 400
last_read_ms     = 0

while True:
    now = ticks_ms()
    iso = ISO_VALUES[iso_idx]

    # ── Button press: cycle menus ─────────────────────────────────────────────
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

    # ── Encoder turn ─────────────────────────────────────────────────────────
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

    # ── Sensor read ───────────────────────────────────────────────────────────
    if ticks_diff(now, last_read_ms) >= READ_INTERVAL_MS:
        last_read_ms = now
        try:
            lux_val  = sensor.lux
            ev_val   = lux_to_ev(lux_val, iso)
            overflow = False
            ev_history.pop(0)
            ev_history.append(ev_val)
        except RuntimeError:
            overflow = True
        except Exception as e:
            print("Sensor error:", e)

    # ── Draw ──────────────────────────────────────────────────────────────────
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
        elif mode == "SHUTTER":
            draw_shutter_priority(ev_val, iso)
        elif mode == "APERTURE":
            draw_aperture_priority(ev_val, iso)
        elif mode == "GRAPH":
            draw_graph_screen(ev_val)

    sleep_ms(50)