"""Poller for the personal door log API."""

import asyncio
import logging
from homeassistant.core import HomeAssistant

LOGGER = logging.getLogger(__name__)

class DoorLogPoller:
    """Poller for the personal door log API."""

    hass: HomeAssistant
    async_retrieve_personal_door_log = None
    interval: int = 2
    is_polling: bool = False

    def __init__(self,
                 hass: HomeAssistant,
                 poll_function,
                 interval=2):
        """Initialize the poller for tghe personal door log API."""
        self.hass = hass
        self.async_retrieve_personal_door_log = poll_function
        self.interval = interval
        self._task = None

    async def async_wait_for_camera_image(self, location, max_retries=3, delay=2):
        """Wait for the camera image URL to become available with retries."""
        for attempt in range(1, max_retries + 1):
            LOGGER.debug("Waiting for camera image for %s (attempt %d/%d)...", location, attempt, max_retries)
            events = await self.async_retrieve_personal_door_log()
            if events:
                for event in events:
                    if event.get("location") == location and event.get("camera_url"):
                        LOGGER.debug("Camera image for %s is now available: %s", location, event.get("camera_url"))
                        return
            await asyncio.sleep(delay)
        LOGGER.error("Failed to retrieve camera image for %s after %d attempts.", location, max_retries)

    async def async_start(self):
        """Start polling the personal door log."""
        if self.async_retrieve_personal_door_log:
            if not self.is_polling:
                LOGGER.debug("🔄 Polling user's personal door log every %s second%s.",
                             str(self.interval),
                             "" if self.interval == 0 else "s")
                self.is_polling = True

                async def poll_loop():
                    while self.is_polling:
                        events = await self.async_retrieve_personal_door_log()
                        # Check events for any with blank camera URL and wait for image
                        if events:
                            for event in events:
                                location = event.get('location', 'unknown')
                                camera_url = event.get('camera_url', '')
                                if not camera_url:
                                    await self.async_wait_for_camera_image(location)
                        await asyncio.sleep(self.interval)

                self._task = asyncio.create_task(poll_loop())

    async def async_stop(self):
        """Stop polling the personal door log."""
        if self.is_polling and self._task:
            LOGGER.debug("🛑 Stop polling personal door log")
            self.is_polling = False
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                LOGGER.debug("Polling task cancelled")
