from micropython import const
from time import sleep_ms

_TSL2591_ADDR = const(0x29)

_TSL2591_COMMAND_BIT = const(0xA0)

_TSL2591_ENABLE_POWEROFF = const(0x00)
_TSL2591_ENABLE_POWERON  = const(0x01)
_TSL2591_ENABLE_AEN      = const(0x02)
_TSL2591_ENABLE_AIEN     = const(0x10)
_TSL2591_ENABLE_NPIEN    = const(0x80)

_TSL2591_REGISTER_ENABLE    = const(0x00)
_TSL2591_REGISTER_CONTROL   = const(0x01)
_TSL2591_REGISTER_DEVICE_ID = const(0x12)
_TSL2591_REGISTER_CHAN0_LOW = const(0x14)
_TSL2591_REGISTER_CHAN1_LOW = const(0x16)

_TSL2591_LUX_DF    = 408.0
_TSL2591_LUX_COEFB = 1.64
_TSL2591_LUX_COEFC = 0.59
_TSL2591_LUX_COEFD = 0.86

_TSL2591_MAX_COUNT_100MS = const(36863)
_TSL2591_MAX_COUNT       = const(65535)

GAIN_LOW  = const(0x00)   # 1x
GAIN_MED  = const(0x10)   # 25x
GAIN_HIGH = const(0x20)   # 428x
GAIN_MAX  = const(0x30)   # 9876x

INTEGRATIONTIME_100MS = const(0x00)
INTEGRATIONTIME_200MS = const(0x01)
INTEGRATIONTIME_300MS = const(0x02)
INTEGRATIONTIME_400MS = const(0x03)
INTEGRATIONTIME_500MS = const(0x04)
INTEGRATIONTIME_600MS = const(0x05)


class TSL2591:
    def __init__(self, i2c, address=_TSL2591_ADDR):
        self.i2c = i2c
        self.address = address
        self._integration_time = INTEGRATIONTIME_100MS
        self._gain = GAIN_MED

        chip_id = self._read_u8(_TSL2591_REGISTER_DEVICE_ID)
        if chip_id != 0x50:
            raise RuntimeError(
                "TSL2591 not found. Expected chip ID 0x50, got 0x{:02X}".format(chip_id)
            )

        self.gain = GAIN_MED
        self.integration_time = INTEGRATIONTIME_100MS
        self.enable()

    def _write_u8(self, reg, val):
        self.i2c.writeto_mem(
            self.address,
            _TSL2591_COMMAND_BIT | reg,
            bytes([val & 0xFF])
        )

    def _read_u8(self, reg):
        data = self.i2c.readfrom_mem(
            self.address,
            _TSL2591_COMMAND_BIT | reg,
            1
        )
        return data[0]

    def _read_u16LE(self, reg):
        data = self.i2c.readfrom_mem(
            self.address,
            _TSL2591_COMMAND_BIT | reg,
            2
        )
        return data[0] | (data[1] << 8)

    def enable(self):
        self._write_u8(
            _TSL2591_REGISTER_ENABLE,
            _TSL2591_ENABLE_POWERON
            | _TSL2591_ENABLE_AEN
            | _TSL2591_ENABLE_AIEN
            | _TSL2591_ENABLE_NPIEN
        )
        sleep_ms(1)

    def disable(self):
        self._write_u8(_TSL2591_REGISTER_ENABLE, _TSL2591_ENABLE_POWEROFF)

    @property
    def gain(self):
        control = self._read_u8(_TSL2591_REGISTER_CONTROL)
        return control & 0b00110000

    @gain.setter
    def gain(self, val):
        if val not in (GAIN_LOW, GAIN_MED, GAIN_HIGH, GAIN_MAX):
            raise ValueError("Invalid gain setting")
        control = self._read_u8(_TSL2591_REGISTER_CONTROL)
        control &= 0b11001111
        control |= val
        self._write_u8(_TSL2591_REGISTER_CONTROL, control)
        self._gain = val
        sleep_ms(1)

    @property
    def integration_time(self):
        control = self._read_u8(_TSL2591_REGISTER_CONTROL)
        return control & 0b00000111

    @integration_time.setter
    def integration_time(self, val):
        if not (0 <= val <= 5):
            raise ValueError("Invalid integration time")
        control = self._read_u8(_TSL2591_REGISTER_CONTROL)
        control &= 0b11111000
        control |= val
        self._write_u8(_TSL2591_REGISTER_CONTROL, control)
        self._integration_time = val
        sleep_ms(1)

    @property
    def raw_luminosity(self):
        ch0 = self._read_u16LE(_TSL2591_REGISTER_CHAN0_LOW)
        ch1 = self._read_u16LE(_TSL2591_REGISTER_CHAN1_LOW)
        return (ch0, ch1)

    @property
    def full_spectrum(self):
        ch0, ch1 = self.raw_luminosity
        return (ch1 << 16) | ch0

    @property
    def infrared(self):
        _, ch1 = self.raw_luminosity
        return ch1

    @property
    def visible(self):
        ch0, ch1 = self.raw_luminosity
        return ch0 - ch1

    @property
    def lux(self):
        ch0, ch1 = self.raw_luminosity

        atime = 100.0 * self._integration_time + 100.0

        if self._integration_time == INTEGRATIONTIME_100MS:
            max_counts = _TSL2591_MAX_COUNT_100MS
        else:
            max_counts = _TSL2591_MAX_COUNT

        if ch0 >= max_counts or ch1 >= max_counts:
            raise RuntimeError("Sensor overflow. Reduce gain or integration time.")

        again = 1.0
        if self._gain == GAIN_MED:
            again = 25.0
        elif self._gain == GAIN_HIGH:
            again = 428.0
        elif self._gain == GAIN_MAX:
            again = 9876.0

        cpl = (atime * again) / _TSL2591_LUX_DF
        lux1 = (ch0 - (_TSL2591_LUX_COEFB * ch1)) / cpl
        lux2 = ((_TSL2591_LUX_COEFC * ch0) - (_TSL2591_LUX_COEFD * ch1)) / cpl

        return max(lux1, lux2)