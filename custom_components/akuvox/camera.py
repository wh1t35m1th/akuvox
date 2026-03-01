"""Camera platform for akuvox."""

from collections.abc import Callable, Awaitable

from homeassistant.helpers import storage
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.stream import create_stream

from .const import DOMAIN, LOGGER, NAME, VERSION, DATA_STORAGE_KEY


async def async_setup_entry(hass: HomeAssistant,
                            _entry,
                            async_add_devices: Callable[[list], Awaitable[None]]):
    """Set up the camera platform."""
    store = storage.Store(hass, 1, DATA_STORAGE_KEY)
    device_data = await store.async_load()

    if not device_data:
        LOGGER.error("No device data found")
        return

    cameras_data = device_data.get("camera_data")
    if not cameras_data:
        LOGGER.error("No camera data found in device data")
        return

    entities = []
    for camera_data in cameras_data:
        name = str(camera_data["name"]).strip()
        rtsp_url = str(camera_data["video_url"]).strip()
        entities.append(AkuvoxCameraEntity(
            hass=hass,
            name=name,
            rtsp_url=rtsp_url
        ))

    if async_add_devices is None:
        LOGGER.error("async_add_devices is None")
        return

    async_add_devices(entities)
    return True


class AkuvoxCameraEntity(Camera):
    """Akuvox RTSP camera entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        rtsp_url: str,
    ) -> None:
        """Initialize the Akuvox camera."""
        super().__init__()
        LOGGER.debug("Adding Akuvox camera '%s'", name)
        LOGGER.debug("Initial RTSP URL for camera '%s': %s", name, rtsp_url)

        self.hass = hass
        self._name = name
        self._rtsp_url = rtsp_url

        self._attr_unique_id = name
        self._attr_name = name
        self._attr_supported_features = CameraEntityFeature.STREAM
        self._attr_is_streaming = True

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            model=VERSION,
            manufacturer=NAME,
        )

    async def _reload_camera_data(self):
        """Reload camera data from storage."""
        store = storage.Store(self.hass, 1, DATA_STORAGE_KEY)
        device_data = await store.async_load()
        if not device_data:
            LOGGER.warning("No device data found when reloading camera data for '%s'", self._name)
            return None
        cameras_data = device_data.get("camera_data")
        if not cameras_data:
            LOGGER.warning("No camera data found in device data when reloading for '%s'", self._name)
            return None
        return cameras_data

    async def stream_source(self) -> str | None:
        """Return the RTSP stream source URL, updating if changed in storage."""
        cameras_data = await self._reload_camera_data()
        if cameras_data is None:
            return self._rtsp_url

        for camera_data in cameras_data:
            stored_name = str(camera_data.get("name", "")).strip()
            if stored_name == self._name:
                new_rtsp_url = str(camera_data.get("video_url", "")).strip()
                if new_rtsp_url and new_rtsp_url != self._rtsp_url:
                    LOGGER.debug(
                        "Updating RTSP URL for camera '%s' from '%s' to '%s'",
                        self._name, self._rtsp_url, new_rtsp_url
                    )
                    self._rtsp_url = new_rtsp_url
                return self._rtsp_url

        LOGGER.warning("Camera '%s' not found in reloaded data", self._name)
        return self._rtsp_url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the stream."""
        return None
