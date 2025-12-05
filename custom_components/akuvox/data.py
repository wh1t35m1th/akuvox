"""Akuvox Data Class - FIXED VERSION."""
from __future__ import annotations
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import storage

from .const import (
    LOGGER,
    TEMP_KEY_QR_HOST,
    PIC_URL_KEY,
    CAPTURE_TIME_KEY,
    DATA_STORAGE_KEY,
    LOCATIONS_DICT,
)
from .helpers import AkuvoxHelpers

helpers = AkuvoxHelpers()

class AkuvoxData:
    """Data class holding key data from API requests."""

    hass: HomeAssistant = None # type: ignore
    host: str = ""
    location_dict: dict = {}
    subdomain: str = ""
    app_type: str = ""
    auth_token: str = ""
    token: str = ""
    refresh_token: str = ""
    phone_number: str = ""
    wait_for_image_url: bool = False
    rtsp_ip: str = ""
    project_name: str = ""
    camera_data = []
    door_relay_data = []
    door_keys_data = []
    _processing_lock: asyncio.Lock = None  # type: ignore


    def __init__(self,
                 entry: ConfigEntry,
                 hass: HomeAssistant,
                 host: str = None, # type: ignore
                 subdomain: str = None, # type: ignore
                 auth_token: str = None, # type: ignore
                 token: str = None, # type: ignore
                 refresh_token: str = None, # type: ignore
                 country_code: str = None, # type: ignore
                 phone_number: str = None, # type: ignore
                 wait_for_image_url: bool = False):
        """Initialize the Akuvox API client."""

        self.hass = hass if hass else self.hass
        self.host = host if host else self.get_value_for_key(entry, "host", host) # type: ignore
        self.auth_token = auth_token if auth_token else self.get_value_for_key(entry, "auth_token", self.host) # type: ignore
        self.token = token if token else self.get_value_for_key(entry, "token", self.token) # type: ignore
        self.refresh_token = refresh_token if refresh_token else self.get_value_for_key(entry, "refresh_token", self.refresh_token) # type: ignore
        self.phone_number = phone_number if phone_number else self.get_value_for_key(entry, "phone_number", self.phone_number) # type: ignore
        self.wait_for_image_url = wait_for_image_url if wait_for_image_url is not None else bool(self.get_value_for_key(entry, "event_screenshot_options", False) == "wait") # type: ignore

        self.subdomain = subdomain if subdomain else self.get_value_for_key(entry, "subdomain", self.subdomain) # type: ignore
        if subdomain is None:
            if not country_code:
                try:
                    if entry.data:
                        entry_data = dict(entry.data)
                        country_name_code = str(entry_data.get("country", hass.config.country))
                        if country_name_code in LOCATIONS_DICT:
                            self.location_dict = LOCATIONS_DICT.get(country_name_code) # type: ignore
                            self.subdomain = self.location_dict.get("subdomain", "ecloud") # type: ignore
                except Exception as error:
                    LOGGER.debug("Unable to use country due to error: %s", error)
        if subdomain is None:
            self.subdomain = "ecloud"

        # Initialize the processing lock
        self._processing_lock = asyncio.Lock()

        self.hass.add_job(self.async_set_stored_data_for_key, "wait_for_image_url", self.wait_for_image_url)

    def get_value_for_key(self, entry: ConfigEntry, key: str, default):
        """Get the value for a given key. 1st check: configured, 2nd check: options, 3rd check: data."""
        if entry is not None:
            if isinstance(entry, dict):
                if key in entry["configured"]: # type: ignore
                    return entry["configured"][key] # type: ignore
                return default
            override = entry.options.get("override", False) or key == "event_screenshot_options"
            placeholder = entry.data.get(key, None)
            if override:
                return entry.options.get(key, placeholder)
            return placeholder
        return default

    def parse_rest_server_response(self, json_data: dict):
        """Parse the rest_server API response."""
        if json_data is not None and json_data != {}:
            self.host = json_data["rest_server_https"]
            return True
        return self.host is None or len(self.host) == 0

    def parse_sms_login_response(self, json_data: dict):
        """Parse the sms_login API response."""
        if json_data is not None:
            if "auth_token" in json_data:
                self.auth_token = json_data["auth_token"]
            if "token" in json_data:
                self.token = json_data["token"]
            if "refresh_token" in json_data:
                self.refresh_token = json_data["refresh_token"]
            if "rtmp_server" in json_data:
                self.rtsp_ip = json_data["rtmp_server"].split(':')[0]

    def parse_userconf_data(self, json_data: dict):
        """Parse the userconf API response."""
        self.door_relay_data = []
        self.camera_data = []
        if json_data is not None:
            if "app_conf" in json_data:
                self.project_name = json_data["app_conf"]["project_name"].strip()
            if "dev_list" in json_data:
                for dev_data in json_data["dev_list"]:
                    name = dev_data["location"].strip()
                    mac = dev_data["mac"]

                    # Camera
                    if "location" in dev_data and "rtsp_pwd" in dev_data and "mac" in dev_data:
                        password = dev_data["rtsp_pwd"]
                        camera_dict = {
                            "name": name,
                            "video_url": f"rtsp://ak:{password}@{self.rtsp_ip}:554/{mac}"
                        }
                        self.camera_data.append(camera_dict)

                    # Door Relay
                    if "relay" in dev_data:
                        for relay in dev_data["relay"]:
                            relay_id = relay["relay_id"]
                            door_name = relay["door_name"].strip()
                            self.door_relay_data.append({
                                "name": name,
                                "door_name": door_name,
                                "relay_id": relay_id,
                                "mac": mac
                            })

        # Log parsed entities
        if len(self.camera_data) > 0:
            LOGGER.debug("🎥 Cameras parsed:")
            for camera_dict in self.camera_data:
                LOGGER.debug(" - %s", camera_dict.get("name", ""))
        if len(self.door_relay_data) > 0:
            LOGGER.debug("🚪 Door relays parsed:")
            for relay_dict in self.door_relay_data:
                LOGGER.debug(" - %s", relay_dict.get("name", ""))

    def parse_temp_keys_data(self, json_data: list):
        """Parse the getPersonalTempKeyList API response."""
        self.door_keys_data = []
        for door_keys_json in json_data:
            door_keys_data = {}
            door_keys_data["key_id"] = door_keys_json["ID"]
            door_keys_data["description"] = door_keys_json["Description"]
            door_keys_data["key_code"] = door_keys_json["TmpKey"]
            door_keys_data["begin_time"] = door_keys_json["BeginTime"]
            door_keys_data["end_time"] = door_keys_json["EndTime"]
            door_keys_data["access_times"] = door_keys_json["AccessTimes"]
            door_keys_data["allowed_times"] = door_keys_json["AllowedTimes"]
            door_keys_data["each_allowed_times"] = door_keys_json["EachAllowedTimes"]
            door_keys_data["qr_code_url"] = f"https://{TEMP_KEY_QR_HOST}{door_keys_json['QrCodeUrl']}"
            door_keys_data["expired"] = False if door_keys_json["Expired"] else True

            door_keys_data["doors"] = []
            if "Doors" in door_keys_json:
                for door_key_json in door_keys_json["Doors"]:
                    door_keys_data["doors"].append({
                        "door_id": door_key_json["ID"],
                        "key_id": door_key_json["KeyID"],  # Reference to key
                        "relay": door_key_json["Relay"],
                        "mac": door_key_json["MAC"]
                    })

            self.door_keys_data.append(door_keys_data)

        if len(self.door_keys_data) > 0:
            LOGGER.debug("🔑 %s Temp key%s parsed:",
                        str(len(self.door_keys_data)),
                        "s" if len(self.door_keys_data) > 1 else "")
            for door_relay_dict in self.door_relay_data:
                LOGGER.debug(" - '%s', with access to %s door%s",
                             door_relay_dict.get("name", ""),
                             str(len(door_keys_data["doors"])),
                             "" if len(door_keys_data["doors"]) == 1 else "s")

    async def async_wait_for_camera_url(self, door_log: dict, max_wait_seconds: int = 5) -> dict:
        """
        Wait for the camera URL to become available with aggressive polling.
        
        Args:
            door_log: The initial door log entry (may have empty PicUrl)
            max_wait_seconds: Maximum time to wait in seconds (default 5)
            
        Returns:
            door_log with updated PicUrl if found, or original if timeout
        """
        capture_time = door_log.get(CAPTURE_TIME_KEY)
        location = door_log.get("Location", "Unknown")
        
        if not capture_time:
            LOGGER.warning("⚠️ Door log missing CaptureTime, cannot retry for camera URL")
            return door_log
        
        # If we already have a URL, no need to wait
        if door_log.get(PIC_URL_KEY):
            LOGGER.debug("✅ Camera URL already present for %s", location)
            return door_log
        
        LOGGER.info("⏳ Waiting for camera URL for %s (max %ds)...", location, max_wait_seconds)
        
        # Poll every 0.5 seconds for up to max_wait_seconds
        poll_interval = 0.5
        max_attempts = int(max_wait_seconds / poll_interval)
        
        for attempt in range(1, max_attempts + 1):
            await asyncio.sleep(poll_interval)
            
            # Fetch latest door log from API
            try:
                # Import here to avoid circular dependency
                from .api import AkuvoxApiClient
                
                # Get the API client from hass.data
                api_client = None
                from .const import DOMAIN
                if DOMAIN in self.hass.data:
                    for entry_data in self.hass.data[DOMAIN].values():
                        if hasattr(entry_data, 'client'):
                            api_client = entry_data.client
                            break
                
                if not api_client:
                    LOGGER.error("❌ Could not find API client for camera URL retry")
                    break
                
                # Fetch the latest door log
                json_data = await api_client.async_get_personal_door_log()
                
                if json_data and len(json_data) > 0:
                    latest_log = json_data[0]
                    
                    # Check if this is the same event (matching CaptureTime)
                    if latest_log.get(CAPTURE_TIME_KEY) == capture_time:
                        pic_url = latest_log.get(PIC_URL_KEY, "")
                        
                        if pic_url:
                            LOGGER.info("✅ Camera URL found after %.1fs for %s", 
                                      attempt * poll_interval, location)
                            # Update the stored latest door log
                            await self.async_set_stored_data_for_key("latest_door_log", latest_log)
                            return latest_log
                        else:
                            LOGGER.debug("🔄 Attempt %d/%d: Camera URL still empty for %s", 
                                       attempt, max_attempts, location)
                    else:
                        LOGGER.debug("⏭️ Door log changed during retry (new event occurred)")
                        break
                        
            except Exception as e:
                LOGGER.warning("⚠️ Error during camera URL retry: %s", e)
                break
        
        # Timeout reached
        LOGGER.warning("⏱️ Timeout waiting for camera URL for %s after %ds", 
                      location, max_wait_seconds)
        return door_log

    async def async_parse_personal_door_log(self, json_data: list):
        """Parse the getDoorLog API response with improved camera URL handling."""
        if json_data is None or len(json_data) == 0:
            return None
        
        # Use lock to prevent concurrent processing of the same event
        if self._processing_lock.locked():
            LOGGER.debug("🔒 Event processing already in progress, skipping duplicate call")
            return None
        
        async with self._processing_lock:
            new_door_log = json_data[0]
            latest_door_log = await self.async_get_stored_data_for_key("latest_door_log")
            
            # Check if this is a new event
            if latest_door_log is not None and CAPTURE_TIME_KEY in latest_door_log:
                if new_door_log is not None and CAPTURE_TIME_KEY in new_door_log:
                    # Ignore if it's the same event
                    if str(latest_door_log[CAPTURE_TIME_KEY]) == str(new_door_log[CAPTURE_TIME_KEY]):
                        return None
            
            # New event detected!
            location = new_door_log.get("Location", "Unknown")
            initiator = new_door_log.get("Initiator", "Unknown")
            capture_type = new_door_log.get("CaptureType", "Unknown")
            
            LOGGER.info("🚪 New door event: %s at %s (%s)", initiator, location, capture_type)
            
            # Check if camera URL is missing
            pic_url = new_door_log.get(PIC_URL_KEY, "")
            
            if not pic_url:
                LOGGER.warning("📷 Camera URL missing for %s, attempting to retrieve...", location)
                
                # ALWAYS wait for camera URL (with timeout)
                # This ensures we try to get the image before firing the event
                new_door_log = await self.async_wait_for_camera_url(
                    new_door_log, 
                    max_wait_seconds=5  # Configurable timeout
                )
                
                # Log final result
                final_pic_url = new_door_log.get(PIC_URL_KEY, "")
                if final_pic_url:
                    LOGGER.info("✅ Camera URL retrieved successfully for %s", location)
                else:
                    LOGGER.warning("❌ Camera URL unavailable for %s - event will fire without image", location)
            else:
                LOGGER.debug("✅ Camera URL present immediately for %s", location)
            
            # Log the complete event details
            LOGGER.debug("ℹ️ Door event details:")
            LOGGER.debug(" - Initiator: %s", new_door_log.get("Initiator"))
            LOGGER.debug(" - CaptureType: %s", new_door_log.get("CaptureType"))
            LOGGER.debug(" - Location: %s", new_door_log.get("Location"))
            LOGGER.debug(" - Door MAC: %s", new_door_log.get("MAC"))
            LOGGER.debug(" - Door Relay: %s", new_door_log.get("Relay"))
            LOGGER.debug(" - Camera URL: %s", "Present" if new_door_log.get(PIC_URL_KEY) else "Missing")
            
            # Store as the latest door log
            await self.async_set_stored_data_for_key("latest_door_log", new_door_log)
            
            return new_door_log

    ###################

    async def async_set_stored_data_for_key(self, key, value):
        """Store key/value pair to integration's storage."""
        store = storage.Store(self.hass, 1, DATA_STORAGE_KEY)
        stored_data: dict = await store.async_load() # type: ignore
        if stored_data is None:
            stored_data = {}
        stored_data[key] = value
        await store.async_save(stored_data)

    async def async_get_stored_data_for_key(self, key):
        """Store key/value pair to integration's storage."""
        store = storage.Store(self.hass, 1, DATA_STORAGE_KEY)
        stored_data: dict = await store.async_load() # type: ignore
        if stored_data:
            return stored_data.get(key, None)

    ###################

    def get_device_data(self) -> dict:
        """Device data dictionary."""
        return {
            "host": self.host,
            "token": self.token,
            "auth_token": self.auth_token,
            "refresh_token": self.refresh_token,
            "camera_data": self.camera_data,
            "door_relay_data": self.door_relay_data,
            "door_keys_data": self.door_keys_data
        }
