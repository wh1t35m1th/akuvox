"""Camera platform for akuvox."""

from collections.abc import Callable, Awaitable
from urllib.parse import urlparse

from homeassistant.helpers import storage
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.components.camera import Camera, CameraEntityFeature

from .const import DOMAIN, LOGGER, NAME, VERSION, DATA_STORAGE_KEY

GO2RTC_KEY = "go2rtc"
# Standard go2rtc ports — HA offsets these by +10000 (API: 11984, RTSP: 18554)
_GO2RTC_STD_API_PORT = 1984
_GO2RTC_STD_RTSP_PORT = 8554
_GO2RTC_PORT_OFFSET = _GO2RTC_STD_RTSP_PORT - _GO2RTC_STD_API_PORT  # 6570


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

        self.hass = hass
        self._name = name
        self._rtsp_url = rtsp_url
        self._go2rtc_stream_id: str | None = None
        self._go2rtc_host = "127.0.0.1"
        self._go2rtc_rtsp_port = _GO2RTC_STD_RTSP_PORT

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

    async def async_added_to_hass(self) -> None:
        """Register stream with go2rtc when entity is added."""
        await super().async_added_to_hass()
        await self._register_go2rtc()

    async def _register_go2rtc(self) -> None:
        """Register the RTSP stream with go2rtc's REST API using TCP transport."""
        go2rtc_config = self.hass.data.get(GO2RTC_KEY)
        if go2rtc_config is None:
            LOGGER.warning(
                "go2rtc not found in hass.data — camera '%s' will use direct RTSP",
                self._name,
            )
            return

        # Go2RtcConfig exposes 'url' (e.g. http://localhost:11984/) and 'session'
        base_url = getattr(go2rtc_config, "url", None)
        session = getattr(go2rtc_config, "session", None)

        if not base_url:
            LOGGER.warning("go2rtc config has no URL — camera '%s' will use direct RTSP", self._name)
            return

        # Derive the RTSP port from the API port using the standard offset
        # Standard: API=1984, RTSP=8554, offset=6570
        # HA's built-in go2rtc: API=11984, RTSP=18554
        parsed = urlparse(base_url)
        api_port = parsed.port or _GO2RTC_STD_API_PORT
        rtsp_host = parsed.hostname or "127.0.0.1"
        rtsp_port = api_port + _GO2RTC_PORT_OFFSET

        stream_id = self.entity_id
        # Force UDP via #transport=udp — go2rtc defaults to TCP, but Akuvox only
        # echoes client_port correctly for UDP SETUP. TCP causes empty client_port=
        # in the server response, which go2rtc rejects.
        source_url = f"{self._rtsp_url}#transport=udp"
        api_url = f"{base_url.rstrip('/')}/api/streams"

        LOGGER.debug(
            "Registering '%s' with go2rtc: api=%s rtsp=%s:%d stream_id='%s'",
            self._name, api_url, rtsp_host, rtsp_port, stream_id,
        )

        try:
            if session is None:
                session = async_get_clientsession(self.hass)
            async with session.put(
                api_url,
                params={"name": stream_id, "src": source_url},
            ) as resp:
                body = await resp.text()
                LOGGER.debug(
                    "go2rtc API response for '%s': status=%d body=%s",
                    self._name, resp.status, body,
                )
                if resp.status not in (200, 204):
                    LOGGER.warning(
                        "go2rtc API returned %d for camera '%s': %s",
                        resp.status, self._name, body,
                    )
                    return

            self._go2rtc_stream_id = stream_id
            self._go2rtc_host = rtsp_host
            self._go2rtc_rtsp_port = rtsp_port
            LOGGER.debug(
                "go2rtc registration OK for '%s' → rtsp://%s:%d/%s",
                self._name, rtsp_host, rtsp_port, stream_id,
            )
        except Exception as err:
            LOGGER.warning(
                "go2rtc registration failed for camera '%s': %s — falling back to direct RTSP",
                self._name, err,
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
        """Return the stream source URL.

        Routes through go2rtc when registered, so ffmpeg receives a clean
        re-served RTSP stream instead of connecting directly to the Akuvox
        server (which produces 'Invalid data found when processing input').
        """
        if self._go2rtc_stream_id:
            url = f"rtsp://{self._go2rtc_host}:{self._go2rtc_rtsp_port}/{self._go2rtc_stream_id}"
            LOGGER.debug("stream_source for '%s': go2rtc relay → %s", self._name, url)
            return url

        # Fallback: direct RTSP (reload URL from storage in case it changed)
        LOGGER.debug("stream_source for '%s': direct RTSP fallback", self._name)
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
