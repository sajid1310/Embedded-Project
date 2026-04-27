from machine import Pin
from time import ticks_ms, ticks_diff

class RotaryEncoder:
    def __init__(self, clk_pin, dt_pin, sw_pin):
        self.clk = Pin(clk_pin, Pin.IN)
        self.dt  = Pin(dt_pin,  Pin.IN)
        self.sw  = Pin(sw_pin,  Pin.IN)

        self._last_clk      = self.clk.value()
        self.delta          = 0
        self.pressed        = False
        self.long_pressed   = False
        self._last_sw_time  = 0
        self._sw_down_time  = 0
        self._sw_held       = False
        self._last_rot_time = 0
        self._DEBOUNCE_MS   = 200
        self._ROT_DEBOUNCE_MS = 50
        self._LONG_PRESS_MS = 800   # hold 800ms = long press

        self.clk.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
                     handler=self._clk_handler)
        self.sw.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
                    handler=self._sw_handler)

    def _clk_handler(self, pin):
        now = ticks_ms()
        if ticks_diff(now, self._last_rot_time) < self._ROT_DEBOUNCE_MS:
            return
        clk_val = self.clk.value()
        if clk_val != self._last_clk:
            self._last_clk = clk_val
            if clk_val == 0:
                if self.dt.value() == 1:
                    self.delta += 1
                else:
                    self.delta -= 1
                self._last_rot_time = now

    def _sw_handler(self, pin):
        now = ticks_ms()
        if self.sw.value() == 0:
            # Button just pressed down
            if ticks_diff(now, self._last_sw_time) > self._DEBOUNCE_MS:
                self._sw_down_time = now
                self._sw_held = True
        else:
            # Button just released
            if self._sw_held:
                held_ms = ticks_diff(now, self._sw_down_time)
                if held_ms >= self._LONG_PRESS_MS:
                    self.long_pressed = True
                else:
                    self.pressed = True
                self._sw_held = False
                self._last_sw_time = now

    def get_delta(self):
        d = self.delta
        self.delta = 0
        return d

    def get_pressed(self):
        p = self.pressed
        self.pressed = False
        return p

    def get_long_pressed(self):
        lp = self.long_pressed
        self.long_pressed = False
        return lp