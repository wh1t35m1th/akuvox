"""Button platform for akuvox."""
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import storage
from homeassistant.helpers.entity import DeviceInfo

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
    """Set up the door relay platform."""
    coordinator: AkuvoxDataUpdateCoordinator
    for _key, value in hass.data[DOMAIN].items():
        coordinator = value
    client = coordinator.client

    store = storage.Store(hass, 1, DATA_STORAGE_KEY)
    device_data: dict = await store.async_load() # type: ignore
    door_relay_data = device_data["door_relay_data"]

    entities = []
    for door_relay in door_relay_data:
        name = door_relay["name"]
        mac = door_relay["mac"]
        relay_id = door_relay["relay_id"]
        data = f"mac={mac}&relay={relay_id}"

        entities.append(
            AkuvoxDoorRelayEntity(
                client=client,
                entry=entry,
                name=name,
                relay_id=relay_id,
                data=data,
            )
        )

    async_add_devices(entities)


class AkuvoxDoorRelayEntity(ButtonEntity, AkuvoxEntity):
    """Akuvox door relay class."""

    _client: AkuvoxApiClient
    _name: str = ""
    _relay_data: str = ""

    def __init__(
        self,
        client: AkuvoxApiClient,
        entry,
        name: str,
        relay_id: str,
        data: str,
    ) -> None:
        """Initialize the Akuvox door relay class."""
        super(ButtonEntity, self).__init__(client=client, entry=entry)
        AkuvoxEntity.__init__(
            self=self,
            client=client,
            entry=entry
        )
        unique_name = name + ", " + relay_id
        self._client = client
        self._name = unique_name
        self._relay_data = data
        # Note: host and token are NOT cached here — they are read live from
        # client._data at press time so they always reflect the current valid values.

        self._attr_unique_id = unique_name
        self._attr_name = unique_name

        LOGGER.debug("Adding Akuvox door relay '%s'", unique_name)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},  # type: ignore
            name=name,
            model=VERSION,
            manufacturer=NAME,
        )

    def press(self) -> None:
        """Sync fallback that calls async version safely."""
        self.hass.loop.create_task(self.async_press())

    async def async_press(self) -> None:
        """Trigger the door relay using the live host from the API client."""
        host = self._client._data.host
        if not host:
            LOGGER.error("❌ Cannot open door '%s': host address is not set", self._name)
            return
        await self._client.async_make_opendoor_request(
            name=self._name,
            host=host,
            data=self._relay_data
        )
