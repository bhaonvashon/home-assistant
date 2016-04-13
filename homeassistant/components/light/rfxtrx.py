"""
Support for RFXtrx lights.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/light.rfxtrx/
"""
from threading import Timer
import logging
import time

import homeassistant.components.rfxtrx as rfxtrx
from homeassistant.components.light import (Light, ATTR_BRIGHTNESS,
                                            ATTR_TRANSITION)

DEPENDENCIES = ['rfxtrx']
UPDATE_INTERVAL = 0.1

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = rfxtrx.DEFAULT_SCHEMA


def setup_platform(hass, config, add_devices_callback, discovery_info=None):
    """Setup the RFXtrx platform."""
    import RFXtrx as rfxtrxmod

    lights = rfxtrx.get_devices_from_config(config, RfxtrxLight)
    add_devices_callback(lights)

    def light_update(event):
        """Callback for light updates from the RFXtrx gateway."""
        if not isinstance(event.device, rfxtrxmod.LightingDevice) or \
                not event.device.known_to_be_dimmable:
            return

        new_device = rfxtrx.get_new_device(event, config, RfxtrxLight)
        if new_device:
            add_devices_callback([new_device])

        rfxtrx.apply_received_command(event)

    # Subscribe to main rfxtrx events
    if light_update not in rfxtrx.RECEIVED_EVT_SUBSCRIBERS:
        rfxtrx.RECEIVED_EVT_SUBSCRIBERS.append(light_update)


class RfxtrxLight(rfxtrx.RfxtrxDevice, Light):
    """Represenation of a RFXtrx light."""

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    def turn_on(self, **kwargs):
        """Turn the light on."""
        self._stop_transition()

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        transition = kwargs.get(ATTR_TRANSITION)

        if transition is None or transition == 0:
            if brightness is None:
                self._brightness = 255
                self._send_command("turn_on")
            else:
                if int(brightness) == self._brightness:
                    return
                self._brightness = brightness
                _brightness = (brightness * 100 // 255)
                self._send_command("dim", _brightness)
            return

        if brightness is None:
            brightness = 255

        brightness_step = (brightness-self._brightness)\
            / (transition/UPDATE_INTERVAL)
        self._transition_update(brightness_step, brightness)

    def turn_off(self, **kwargs):
        """Turn the light off."""
        self._stop_transition()

        transition = kwargs.get(ATTR_TRANSITION)
        if transition is None or transition == 0:
            rfxtrx.RfxtrxDevice.turn_off(self, **kwargs)
            return
        brightness = kwargs.get(ATTR_BRIGHTNESS, 0)

        brightness_step = (brightness-self._brightness)\
            / (transition/UPDATE_INTERVAL)
        self._transition_update(brightness_step, brightness)

    def update_state(self, state, brightness=0):
        """Update det state of the device."""
        self._stop_transition()
        rfxtrx.RfxtrxDevice.update_state(self, state, brightness)

    def _transition_update(self, brightness_step, target_brightness):
        new_brightness = self._brightness + brightness_step
        if brightness_step > 0 and new_brightness >= target_brightness:
            self.turn_on(brightness=target_brightness)
            return
        elif brightness_step < 0 and new_brightness <= target_brightness:
            if target_brightness > 0:
                self.turn_on(brightness=target_brightness)
            else:
                self.turn_off()
            return

        self.turn_on(brightness=int(new_brightness))

        args = (brightness_step, target_brightness)
        self.transition_timer = \
            Timer(UPDATE_INTERVAL, self._transition_update, args)
        self.transition_timer.start()

    def _stop_transition(self):
        if self.transition_timer is None:
            return
        self.transition_timer.cancel()
        while not self.transition_timer.finished:
            time.sleep(0.05)
