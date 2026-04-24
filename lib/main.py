from machine import SoftI2C, Pin
from time import sleep
from ESII import tsl2591

i2c = SoftI2C(
    sda=Pin(11, pull=Pin.PULL_UP),
    scl=Pin(12, pull=Pin.PULL_UP),
    freq=100000
)

print("I2C scan:", [hex(x) for x in i2c.scan()])

sensor = tsl2591.TSL2591(i2c)

# Optional: use lower gain first for stability
sensor.gain = tsl2591.GAIN_LOW
sensor.integration_time = tsl2591.INTEGRATIONTIME_100MS

while True:
    try:
        print("Lux:", sensor.lux)
        print("Infrared:", sensor.infrared)
        print("Visible:", sensor.visible)
        print("Full spectrum:", sensor.full_spectrum)
        print("------")
    except Exception as e:
        print("Read error:", e)
    sleep(0.5)

