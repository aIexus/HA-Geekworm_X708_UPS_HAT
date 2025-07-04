import importlib
import struct
import logging

from time import time, sleep

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_NAME, CONF_MONITORED_CONDITIONS
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

CONF_I2C_ADDRESS = 'i2c_address'
CONF_I2C_BUS = 'i2c_bus'

DEFAULT_NAME = 'UPS Sensor'
DEFAULT_I2C_ADDRESS = 0x36
DEFAULT_I2C_BUS = 1

SENSOR_VOLTAGE = 'voltage'
SENSOR_CAPACITY = 'capacity'
SENSOR_TYPES = {
    SENSOR_VOLTAGE: ['Voltage', 'V'],
    SENSOR_CAPACITY: ['Capacity', '%'],
}

DEFAULT_MONITORED = [SENSOR_VOLTAGE, SENSOR_CAPACITY]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(
            CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS
        ): cv.positive_int,
        vol.Optional(
            CONF_MONITORED_CONDITIONS, default=DEFAULT_MONITORED
        ): vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
        vol.Optional(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): cv.positive_int,
    }
)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):
    """Set up the UPS Sensor"""
    name = config.get(CONF_NAME)

    sensor_handler = await hass.async_add_executor_job(_setup_UPS, config)
    if sensor_handler is None:
        return

    dev = []
    for variable in config[CONF_MONITORED_CONDITIONS]:
        dev.append(
            UPSSensor(
                sensor_handler, variable, SENSOR_TYPES[variable][1], name
            )
        )

    async_add_entities(dev)
    return


def _setup_UPS(config):
    """Set up and configure the UPS Sensor"""
    from smbus import SMBus

    sensor_handler = None
    try:
        i2c_address = config.get(CONF_I2C_ADDRESS)
        bus = SMBus(config.get(CONF_I2C_BUS))
        sensor = UPS(i2c_address, bus)

    except (RuntimeError, IOError):
        _LOGGER.error('UPS sensor not detected at 0x%02x', i2c_address)
        return None

    sensor_handler = UPSHandler(sensor)

    sleep(0.5)  # Wait for device to stabilize
    if not sensor_handler.sensor_data.voltage:
        _LOGGER.error('UPS sensor failed to Initialize')
        return None

    return sensor_handler


class UPSHandler:
    """UPS sensor working in i2C bus"""

    class SensorData:
        """Sensor data representation"""

        def __init__(self):
            """Initialize the sensor data object"""
            self.voltage = None
            self.capacity = None

    def __init__(self, sensor):
        """Initialize the sensor handler"""
        self.sensor_data = UPSHandler.SensorData()
        self._sensor = sensor

        self.update(first_read=True)

    def update(self, first_read=False):
        """Read sensor data"""
        if first_read:
            # Attempt first read, it almost always fails first attempt
            self._sensor.get_sensor_data()
        if self._sensor.get_sensor_data():
            self.sensor_data.voltage = self._sensor.data.voltage
            self.sensor_data.capacity = self._sensor.data.capacity


class UPSSensor(Entity):
    """Implementation of the UPS Sensor"""

    def __init__(self, UPS_client, sensor_type, temp_unit, name):
        """Initialize the sensor"""
        self.client_name = name
        self._name = SENSOR_TYPES[sensor_type][0]
        self.UPS_client = UPS_client
        self.temp_unit = temp_unit
        self.type = sensor_type
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    @property
    def name(self):
        """Return the name of the sensor"""
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        """Return the state of the sensor"""
        return self._state

    @property
    def icon(self):
        """Return the icon of the sensor"""
        if self.type == SENSOR_VOLTAGE:
            return 'mdi:sine-wave'
        elif self.type == SENSOR_CAPACITY:
            if isinstance(self._state, int) or isinstance(self._state, float):
                if self._state >= 80:
                    return 'mdi:battery-high'
                elif self._state >= 50:
                    return 'mdi:battery-medium'
		elif self._state >= 20
		    return 'mdi:battery-low' 
                else:
                    return 'mdi:battery-alert'
            else:
                return 'mdi:battery-unknown'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor"""
        return self._unit_of_measurement

    async def async_update(self):
        """Get the latest data from the UPS and update the states."""
        await self.hass.async_add_executor_job(self.UPS_client.update)
        if self.type == SENSOR_VOLTAGE:
            self._state = round(self.UPS_client.sensor_data.voltage, 2)
        elif self.type == SENSOR_CAPACITY:
            self._state = round(self.UPS_client.sensor_data.capacity)


class FieldData:
    """Structure for storing UPS sensor data"""

    def __init__(self):
        self.status = None
        self.voltage = False
        self.capacity = None


class UPSData:
    """Structure to represent UPS device"""

    def __init__(self):
        self.data = FieldData()


class UPS(UPSData):
    def __init__(self, i2c_addr=DEFAULT_I2C_ADDRESS, i2c_device=None):
        UPSData.__init__(self)

        self.i2c_addr = i2c_addr
        self._i2c = i2c_device
        if self._i2c is None:
            import smbus

            self._i2c = smbus.SMBus(1)

        self.get_sensor_data()

    def get_sensor_data(self):
        """Get sensor data.
        Stores data in .data and returns True upon success.
        """

        read = self._i2c.read_word_data(self.i2c_addr, 2)
        swapped = struct.unpack('<H', struct.pack('>H', read))[0]
        self.data.voltage = swapped * 1.25 / 1000 / 16,

        read = self._i2c.read_word_data(self.i2c_addr, 4)
        swapped = struct.unpack('<H', struct.pack('>H', read))[0]
        self.data.capacity = swapped / 256

        return True
