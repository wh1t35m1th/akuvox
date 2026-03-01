"""Sensor platform for akuvox."""
from datetime import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import storage
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .api import AkuvoxApiClient
from .coordinator import AkuvoxDataUpdateCoordinator
from .const import (
    DOMAIN,
    LOGGER,
    NAME,
    VERSION,
    DATA_STORAGE_KEY
)
from .entity import AkuvoxEntity

async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the temporary door key platform and token sensor."""
    coordinator: AkuvoxDataUpdateCoordinator
    for _key, value in hass.data[DOMAIN].items():
        coordinator = value
    client = coordinator.client
    store = storage.Store(hass, 1, DATA_STORAGE_KEY)
    device_data: dict = await store.async_load() # type: ignore
    door_keys_data = device_data["door_keys_data"]
    date_format = "%d-%m-%Y %H:%M:%S"

    entities = []
    for door_key_data in door_keys_data:
        key_id = door_key_data["key_id"]
        description = door_key_data["description"]
        key_code=door_key_data["key_code"]
        begin_time = datetime.strptime(str(door_key_data["begin_time"]), date_format)
        end_time = datetime.strptime(str(door_key_data["end_time"]), date_format)
        allowed_times=door_key_data["allowed_times"]
        access_times=door_key_data["access_times"]
        qr_code_url=door_key_data["qr_code_url"]

        entities.append(
            AkuvoxTemporaryDoorKey(
                client=client,
                entry=entry,
                key_id=key_id,
                description=description,
                key_code=key_code,
                begin_time=begin_time,
                end_time=end_time,
                allowed_times=allowed_times,
                access_times=access_times,
                qr_code_url=qr_code_url,
            )
        )

    entities.append(AkuvoxTokenSensor(client=client, entry=entry))
    entities.append(AkuvoxLastDoorEventSensor(hass=hass, client=client, entry=entry))

    async_add_devices(entities)

class AkuvoxTemporaryDoorKey(SensorEntity, AkuvoxEntity):
    """Akuvox temporary door key class."""

    def __init__(
        self,
        client: AkuvoxApiClient,
        entry,
        key_id: str,
        description: str,
        key_code: str,
        begin_time: datetime,
        end_time: datetime,
        allowed_times: int,
        access_times: int,
        qr_code_url) -> None:
        """Initialize the Akuvox door relay class."""
        super(SensorEntity, self).__init__(client=client, entry=entry)
        AkuvoxEntity.__init__(
            self=self,
            client=client,
            entry=entry
        )
        self.client = client
        self.key_id = key_id
        self.description = description
        self.key_code = key_code
        self.begin_time = begin_time
        self.end_time = end_time
        self.allowed_times = allowed_times
        self.access_times = access_times
        self.qr_code_url = qr_code_url
        self.expired = False

        name = f"{self.description} {self.key_id}".strip()
        self._attr_unique_id = name
        self._attr_name = name
        self._attr_key_code = key_code

        self._attr_extra_state_attributes = self.to_dict()

        LOGGER.debug("Adding temporary door key '%s'", self._attr_unique_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Temporary Keys")},  # type: ignore
            name="Temporary Keys",
            model=VERSION,
            manufacturer=NAME,
        )

    def is_key_active(self):
        """Check if the key is currently active based on the begin_time and end_time."""
        current_time = datetime.now()
        return self.begin_time <= current_time <= self.end_time

    def to_dict(self):
        """Convert the object to a dictionary for easy serialization."""
        return {
            'key_id': self.key_id,
            'description': self.description,
            'key_code': self.key_code,
            'enabled': self.is_key_active(),
            'begin_time': self.begin_time,
            'end_time': self.end_time,
            'access_times': self.access_times,
            'allowed_times': self.allowed_times,
            'qr_code_url': self.qr_code_url,
            'expired': not self.is_key_active()
        }

class AkuvoxLastDoorEventSensor(SensorEntity, AkuvoxEntity):
    """Sensor that tracks the last door event timestamp and metadata."""

    def __init__(self, hass, client: AkuvoxApiClient, entry) -> None:
        """Initialize the last door event sensor."""
        super().__init__(client=client, entry=entry)
        self._attr_name = "Akuvox Last Door Event"
        self._attr_unique_id = "akuvox_last_door_event_sensor"
        self._attr_icon = "mdi:door-open"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Akuvox Last Door Event")},
            name="Akuvox Last Door Event",
            model=VERSION,
            manufacturer=NAME,
        )
        self._hass = hass
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        """Register listener for door update events."""
        await super().async_added_to_hass()

        # Pre-populate from the latest stored door log so the sensor
        # has a value immediately after a HA restart.
        try:
            store = storage.Store(self._hass, 1, DATA_STORAGE_KEY)
            stored_data: dict = await store.async_load() or {}
            latest_log = stored_data.get("latest_door_log")
            if latest_log:
                self._apply_door_log(latest_log)
        except Exception as err:
            LOGGER.debug("Could not pre-load last door log: %s", err)

        @callback
        def _handle_door_event(event):
            """Handle incoming akuvox_door_update events."""
            self._apply_door_log(event.data)
            self.async_write_ha_state()

        self._unsub = self._hass.bus.async_listen(
            "akuvox_door_update", _handle_door_event
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister event listener on removal."""
        if self._unsub:
            self._unsub()

    def _apply_door_log(self, door_log: dict) -> None:
        """Extract fields from a door log entry into sensor state/attributes."""
        raw_time = door_log.get("CaptureTime", "")
        location = door_log.get("Location", "")
        initiator = door_log.get("Initiator", "")
        capture_type = door_log.get("CaptureType", "")
        pic_url = door_log.get("PicUrl", "")
        mac = door_log.get("MAC", "")
        relay = door_log.get("Relay", "")

        # Parse the timestamp so HA can display it nicely
        parsed_time = None
        if raw_time:
            for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed_time = datetime.strptime(raw_time, fmt)
                    break
                except ValueError:
                    continue

        # The sensor's primary value is the human-readable timestamp string
        self._attr_native_value = raw_time if raw_time else None

        self._attr_extra_state_attributes = {
            "location": location,
            "initiator": initiator,
            "capture_type": capture_type,
            "pic_url": pic_url,
            "mac": mac,
            "relay": relay,
            "parsed_time": parsed_time.isoformat() if parsed_time else None,
        }


class AkuvoxTokenSensor(SensorEntity, AkuvoxEntity):
    """Sensor to display a masked view of the Akuvox API token."""

    def __init__(self, client: AkuvoxApiClient, entry) -> None:
        """Initialize the Akuvox token sensor."""
        super().__init__(client=client, entry=entry)
        self._attr_name = "Akuvox Token"
        self._attr_unique_id = "akuvox_token_sensor"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:key-chain"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Akuvox Token")},
            name="Akuvox Token",
            model=VERSION,
            manufacturer=NAME,
        )

    @property
    def native_value(self):
        """Return the masked Akuvox API token."""
        token = getattr(self.client._data, "token", None)
        if token and len(token) > 14:
            return f"{token[:8]}...{token[-6:]}"
        elif token:
            # If token is shorter than 15 chars, show as is
            return token
        else:
            return "Unavailable"
