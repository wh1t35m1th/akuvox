"""Custom integration to integrate akuvox with Home Assistant.

For more details about this integration, please refer to
https://github.com/nimroddolev/akuvox
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .config_flow import AkuvoxOptionsFlowHandler
from .api import AkuvoxApiClient
from .const import (
    DOMAIN,
    LOGGER
)
from .coordinator import AkuvoxDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.CAMERA,
    Platform.BUTTON,
    Platform.SENSOR
]

# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})

    api_client = AkuvoxApiClient(
        session=async_get_clientsession(hass),
        hass=hass,
        entry=entry,
    )

    coordinator = AkuvoxDataUpdateCoordinator(hass=hass, client=api_client)
    coordinator.config_entry = entry
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Step 1: Load config entry values into memory.
    await async_update_configuration(hass=hass, entry=entry, log_values=True)

    # Step 2: Determine the best token to use.
    # entry.options always holds the most recently user-configured token.
    # Persistent storage holds auto-refreshed tokens from previous sessions.
    # Priority: options token wins IF it differs from stored (user just updated it).
    # Otherwise use stored (which may be newer from a previous auto-refresh).
    try:
        options_token = entry.options.get("token", "")
        options_refresh = entry.options.get("refresh_token", "")

        stored_token = await api_client._data.async_get_stored_data_for_key("token")
        stored_refresh = await api_client._data.async_get_stored_data_for_key("refresh_token")

        LOGGER.debug("🔍 options_token: %s", options_token[:10] if options_token else "None")
        LOGGER.debug("🔍 stored_token:  %s", stored_token[:10] if stored_token else "None")
        LOGGER.debug("🔍 options_refresh: %s", options_refresh[:10] if options_refresh else "None")
        LOGGER.debug("🔍 stored_refresh:  %s", stored_refresh[:10] if stored_refresh else "None")

        # Token selection: options wins if different from stored (user just reconfigured).
        # If they're the same or stored is absent, use options.
        # Only use stored if options is absent.
        if options_token and options_token != stored_token:
            # User entered a new token via Configure — trust it and update storage
            LOGGER.debug("✅ options_token differs from stored — user reconfigured. Using options token: %s...", options_token[:10])
            api_client._data.token = options_token
            await api_client._data.async_set_stored_data_for_key("token", options_token)
        elif options_token:
            # Same as stored — use options (they match, doesn't matter which)
            LOGGER.debug("✅ options_token matches stored — using: %s...", options_token[:10])
            api_client._data.token = options_token
        elif stored_token:
            # No options token at all — fall back to stored
            LOGGER.debug("✅ No options token — using stored token: %s...", stored_token[:10])
            api_client._data.token = stored_token

        # Same logic for refresh token
        if options_refresh and options_refresh != stored_refresh:
            LOGGER.debug("✅ options_refresh differs from stored — user reconfigured. Using options refresh: %s...", options_refresh[:10])
            api_client._data.refresh_token = options_refresh
            await api_client._data.async_set_stored_data_for_key("refresh_token", options_refresh)
        elif options_refresh:
            LOGGER.debug("✅ options_refresh matches stored — using: %s...", options_refresh[:10])
            api_client._data.refresh_token = options_refresh
        elif stored_refresh:
            LOGGER.debug("✅ No options refresh — using stored refresh_token: %s...", stored_refresh[:10])
            api_client._data.refresh_token = stored_refresh

    except Exception as e:
        LOGGER.warning("⚠️ Failed to load/sync stored token data on startup: %s", e)

    LOGGER.debug("🔑 Token after config load: %s...", api_client._data.token[:10] if api_client._data.token else "None")

    # Step 3: Use refresh_token to obtain fresh tokens (keeps session alive across HA restarts).
    if api_client._data.refresh_token:
        LOGGER.debug("🔄 Refresh token found - attempting token refresh on startup...")
        try:
            if await api_client.async_refresh_token():
                LOGGER.debug("✅ Startup token refresh succeeded - session restored.")
            else:
                LOGGER.warning("⚠️ Startup token refresh failed - will use existing token.")
        except Exception as e:
            LOGGER.error("❌ Exception during startup token refresh: %s", str(e))
    else:
        LOGGER.debug("ℹ️ No refresh token available - using existing token as-is.")

    LOGGER.debug("🔑 Active token after startup: %s...", api_client._data.token[:10] if api_client._data.token else "None")

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    api_client: AkuvoxApiClient = get_api_client(hass=hass)
    if api_client and hasattr(api_client, 'door_log_poller'):
        await api_client.async_stop_polling()
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


# Polling

async def async_stop_polling(hass: HomeAssistant):
    """Stop polling the personal door log API."""
    api_client: AkuvoxApiClient = get_api_client(hass=hass) # type: ignore
    if api_client and hasattr(api_client, 'door_log_poller'):
        await api_client.async_stop_polling()

async def async_start_polling(hass: HomeAssistant):
    """Start polling the personal door log API."""
    api_client: AkuvoxApiClient = get_api_client(hass=hass) # type: ignore
    await api_client.async_start_polling_personal_door_log()

def get_api_client(hass: HomeAssistant):
    """Akuvox API Client."""
    for _key, value in hass.data[DOMAIN].items():
        coordinator: AkuvoxDataUpdateCoordinator = value
        return coordinator.client

# Integration options

async def async_options(self, entry: ConfigEntry):
    """Present current configuration options for modification."""
    return AkuvoxOptionsFlowHandler(entry)

async def async_options_updated(self, entry: ConfigEntry):
    """Handle updated configuration options and update the entry."""
    LOGGER.debug("Updated Options: %s", str(entry.options))

# Update

async def async_update_configuration(hass: HomeAssistant, entry: ConfigEntry, log_values: bool = False) -> None:
    """Update stored values from configuration."""
    try:
        if entry.options:
            updated_options: dict = entry.options.copy()
            updated_options["wait_for_image_url"] = bool(updated_options.get("event_screenshot_options", "") == "wait")

            coordinator: AkuvoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
            client: AkuvoxApiClient = coordinator.client

            if log_values:
                LOGGER.debug("Configured values:")
                for key, value in updated_options.items():
                    if value:
                        client.update_data(key, value)
                        LOGGER.debug(" - %s = %s", key, value)
            else:
                for key, value in updated_options.items():
                    if value:
                        client.update_data(key, value)

    except Exception as error:
        LOGGER.warning("Unable to update configuration: %s", str(error))

# Services
async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the Akuvox integration."""

    async def async_update_tokens_service(call):
        """Handle the update_tokens service call."""
        entry_id = call.data.get("entry_id")
        token = call.data.get("token")
        refresh_token = call.data.get("refresh_token", "")

        if not entry_id or not token:
            LOGGER.error("❌ Service call missing required parameters: entry_id and token")
            return

        if DOMAIN not in hass.data or entry_id not in hass.data[DOMAIN]:
            LOGGER.error("❌ Entry ID %s not found", entry_id)
            return

        coordinator: AkuvoxDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        client: AkuvoxApiClient = coordinator.client

        try:
            old_token = client._data.token[:10] + "..." if len(client._data.token) > 10 else client._data.token
            client._data.token = token
            if refresh_token:
                client._data.refresh_token = refresh_token

            await client._data.async_set_stored_data_for_key("token", token)
            if refresh_token:
                await client._data.async_set_stored_data_for_key("refresh_token", refresh_token)

            new_token = client._data.token[:10] + "..." if len(client._data.token) > 10 else client._data.token
            LOGGER.info("✅ Tokens updated successfully via service call")
            LOGGER.debug("   Old token: %s", old_token)
            LOGGER.debug("   New token: %s", new_token)

            if await client.async_retrieve_user_data():
                LOGGER.info("✅ Token validation successful - user data retrieved")
            else:
                LOGGER.warning("⚠️ Token validation failed - unable to retrieve user data")

        except Exception as error:
            LOGGER.error("❌ Failed to update tokens: %s", error)

    async def async_refresh_tokens_service(call):
        """Handle the refresh_tokens service call."""
        entry_id = call.data.get("entry_id")

        if not entry_id:
            LOGGER.error("❌ Service call missing required parameter: entry_id")
            return

        if DOMAIN not in hass.data or entry_id not in hass.data[DOMAIN]:
            LOGGER.error("❌ Entry ID %s not found", entry_id)
            return

        coordinator: AkuvoxDataUpdateCoordinator = hass.data[DOMAIN][entry_id]
        client: AkuvoxApiClient = coordinator.client

        try:
            if await client.async_refresh_token():
                LOGGER.info("✅ Tokens refreshed successfully via service call")
            else:
                LOGGER.error("❌ Token refresh failed")
        except Exception as error:
            LOGGER.error("❌ Failed to refresh tokens: %s", error)

    hass.services.async_register(DOMAIN, "update_tokens", async_update_tokens_service, schema=None)
    hass.services.async_register(DOMAIN, "refresh_tokens", async_refresh_tokens_service, schema=None)
