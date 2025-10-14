"""Akuvox API Client."""
from __future__ import annotations

import asyncio
import socket
import json

from homeassistant.core import HomeAssistant

import aiohttp
import httpx
import async_timeout
import requests

from .data import AkuvoxData
from .door_poll import DoorLogPoller

from .const import (
    LOGGER,
    REST_SERVER_ADDR,
    REST_SERVER_PORT,
    API_SEND_SMS,
    SMS_LOGIN_API_VERSION,
    API_SMS_LOGIN,
    API_SERVERS_LIST,
    REST_SERVER_API_VERSION,
    API_REST_SERVER_DATA,
    USERCONF_API_VERSION,
    API_USERCONF,
    OPENDOOR_API_VERSION,
    API_OPENDOOR,
    API_REFRESH_TOKEN,
    TOKEN_REFRESH_INTERVAL_DAYS,
    API_APP_HOST,
    API_GET_PERSONAL_TEMP_KEY_LIST,
    API_GET_PERSONAL_DOOR_LOG
)


class AkuvoxApiClientError(Exception):
    """Exception to indicate a general API error."""


class AkuvoxApiClientCommunicationError(AkuvoxApiClientError):
    """Exception to indicate a communication error."""


class AkuvoxApiClientAuthenticationError(AkuvoxApiClientError):
    """Exception to indicate an authentication error."""

class AkuvoxApiClient:
    """Sample API Client."""

    _data: AkuvoxData = None # type: ignore
    hass: HomeAssistant
    door_log_poller: DoorLogPoller

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hass: HomeAssistant,
        entry,
    ) -> None:
        """Akuvox API Client."""
        self._session = session
        self.hass = hass
        if entry:
            LOGGER.debug("▶️ Initializing AkuvoxData from API client init")
            self._data = AkuvoxData(
                entry=entry,
                hass=hass) # type: ignore

    async def async_init_api(self) -> bool:
        """Initialize API configuration data."""
        # Load refresh token from storage if not already set
        if not self._data.refresh_token:
            stored_refresh_token = await self._data.async_get_stored_data_for_key("refresh_token")
            if stored_refresh_token:
                self._data.refresh_token = stored_refresh_token
                LOGGER.debug("📱 Loaded refresh token from storage")
                LOGGER.debug("🔐 Loaded refresh_token from storage: %s", stored_refresh_token)

        # Check and refresh tokens if needed
        if self._data.refresh_token:
            await self.async_check_and_refresh_tokens()

        if self._data.host is None or len(self._data.host) == 0:
            self._data.host = "...request in process"
            if await self.async_fetch_rest_server() is False:
                return False

        if self._data.rtsp_ip is None:
            if self._data.host is not None and len(self._data.host) > 0:
                if await self.async_make_servers_list_request(
                    hass=self.hass,
                    auth_token=self._data.auth_token,
                    country_code=self.hass.config.country,
                    phone_number=self._data.phone_number) is False:
                    LOGGER.error("❌ API request for servers list failed.")
                    return False
            else:
                LOGGER.error("❌ Unable to find API host address.")
                return False

        # Begin polling personal door log
        await self.async_start_polling()

        return True

    async def async_start_polling(self):
        """Start polling the personal door log API."""
        self.door_log_poller: DoorLogPoller = DoorLogPoller(
            hass=self.hass,
            poll_function=self.async_retrieve_personal_door_log)
        await self.door_log_poller.async_start()

    async def async_stop_polling(self):
        """Stop polling the personal door log API."""
        await self.door_log_poller.async_stop()

    def init_api_with_data(self,
                           hass: HomeAssistant,
                           host=None,
                           subdomain=None,
                           auth_token=None,
                           token=None,
                           phone_number=None,
                           country_code=None):
        """"Initialize values from saved data/options."""
        if not self._data:
            LOGGER.debug("▶️ Initializing AkuvoxData from API client init_api_with_data")
            self._data = AkuvoxData(
                entry=None, # type: ignore
                hass=hass,
                host=host, # type: ignore
                subdomain=subdomain, # type: ignore
                auth_token=auth_token, # type: ignore
                token=token, # type: ignore
                phone_number=phone_number, # type: ignore
                country_code=country_code) # type: ignore
        self.hass = self.hass if self.hass else hass

    ####################
    # API Call Methods #
    ####################

    async def async_fetch_rest_server(self):
        """Retrieve the Akuvox REST server addresses and data."""
        LOGGER.debug("📡 Fetching REST server data...")
        json_data = await self._async_api_wrapper(
            method="get",
            url=f"https://{REST_SERVER_ADDR}:{REST_SERVER_PORT}/{API_REST_SERVER_DATA}",
            data=None,
            headers={
                'api-version': REST_SERVER_API_VERSION
            }
        )
        if json_data is not None:
            LOGGER.debug("✅ REST server data received successfully")
            if self._data.parse_rest_server_response(json_data): # type: ignore
                return True
            LOGGER.error("❌ Unable to parse Akuvox server rest API data.")
        else:
            LOGGER.error("❌ Unable to fetch Akuvox server rest API data.")
        return False

    async def async_send_sms(self, hass:HomeAssistant, country_code, phone_number, subdomain):
        """Request SMS code to user's device."""
        self.init_api_with_data(
            hass=hass,
            subdomain=subdomain,
            country_code=country_code,
            phone_number=phone_number)
        url = f"https://{self._data.host}/{API_SEND_SMS}".replace(".subdomain", f".{subdomain}")
        LOGGER.debug("url = %s", url)
        if await self.async_init_api():
            headers = {
                "Host": self._data.host,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-AUTH-TOKEN": "",
                "Connection": "keep-alive",
                "Accept": "*/*",
                "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
                "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
                "x-cloud-lang": "en"
            }
            data = {
                "AreaCode": country_code,
                "MobileNumber": phone_number,
                "Type": 0
            }
            LOGGER.debug("📡 Requesting SMS code from subdomain %s...", subdomain)
            response = await self._async_api_wrapper(
                method="post",
                url=url,
                headers=headers,
                data=data,
            )
            if response is not None:
                if response["result"] == 0: # type: ignore
                    LOGGER.debug("✅ SMS code request successful")
                    return True

            LOGGER.error("❌ SMS code request unsuccessful. Request URL: %s", url)
        else:
            LOGGER.error("❌ Unable to initialize API. Did you login again from your device? Try logging in/adding tokens again.")
        return False

    async def async_make_servers_list_request(self,
                                              hass: HomeAssistant,
                                              auth_token: str,
                                              country_code,
                                              phone_number: str,
                                              subdomain: str = "") -> bool:
        """Request server list data."""
        self.init_api_with_data(
            hass=hass,
            subdomain=subdomain,
            auth_token=auth_token,
            token=self._data.token,
            country_code=country_code,
            phone_number=phone_number)
        if await self.async_init_api() is False:
            return False

        # Always use the dynamic subdomain for the servers list URL
        url = f"https://gate.{self._data.subdomain}.akuvox.com:{REST_SERVER_PORT}/{API_SERVERS_LIST}"
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "x-auth-token": self._data.token,
            "api-version": "6.8",
            "x-cloud-lang": "en",
            "user-agent": "VBell/7.20.5 (iPhone; iOS 26.1; Scale/2.00)",
            "accept-language": "en-SG;q=1"
        }
        obfuscated_number = str(self.get_obfuscated_phone_number(phone_number))
        data = json.dumps({
            "token": self._data.token,
            "user": obfuscated_number,
        })

        # DEBUG: show which token is being used for server list
        LOGGER.debug("🔑 Using token for server list request: %s", self._data.token)

        LOGGER.debug("📡 Requesting server list...")
        json_data = await self._async_api_wrapper(
            method="post",
            url=url,
            headers=headers,
            data=data,
        )
        if json_data is not None:
            LOGGER.debug("✅ Server list retrieved successfully")
            self._data.parse_sms_login_response(json_data) # type: ignore
            
            # Store refresh token if received from servers_list
            if self._data.refresh_token:
                await self._data.async_set_stored_data_for_key("refresh_token", self._data.refresh_token)
                LOGGER.debug("✅ Refresh token captured and stored from servers_list")
                
            return True

        LOGGER.error("❌ Unable to retrieve server list. Try sigining in again / check that your tokens are valid.")
        return False

    async def async_sms_sign_in(self, phone_number, country_code, sms_code) -> bool:
        """Sign user in with their phone number and SMS code."""

        login_data = await self.async_validate_sms_code(phone_number, country_code, sms_code)
        if login_data is not None:
            self._data.parse_sms_login_response(login_data) # type: ignore

            # Store tokens persistently
            if self._data.refresh_token:
                await self._data.async_set_stored_data_for_key("refresh_token", self._data.refresh_token)
                LOGGER.debug("✅ Refresh token captured and stored from SMS login")
            else:
                LOGGER.warning("⚠️  No refresh token received from SMS login response")

            # Retrieve connected device data
            await self.async_retrieve_device_data()
            await self.async_retrieve_temp_keys_data()

            return True

        return False

    async def async_validate_sms_code(self, phone_number, country_code, sms_code):
        """Validate the SMS code received by the user."""
        LOGGER.debug("📡 Logging in user with phone number and SMS code...")

        obfuscated_number = self.get_obfuscated_phone_number(phone_number)
        params = f"phone={obfuscated_number}&code={sms_code}&area_code={country_code}"
        url = f"https://{REST_SERVER_ADDR}:{REST_SERVER_PORT}/{API_SMS_LOGIN}?{params}"
        data = {}
        headers = {
            'api-version': SMS_LOGIN_API_VERSION,
            'User-Agent': 'VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)'
        }
        response = await self._async_api_wrapper(method="get", url=url, headers=headers, data=data)

        if response is not None:
            LOGGER.debug("✅ Login successful")
            return response

        LOGGER.error("❌ Unable to log in with SMS code.")
        return None

    async def async_retrieve_user_data(self) -> bool:
        """Retrieve user devices and temp keys data."""
        if await self.async_make_servers_list_request(
            hass=self.hass,
            auth_token=self._data.auth_token,
            country_code=self.hass.config.country,
            phone_number=self._data.phone_number):
            await self.async_retrieve_device_data()
            await self.async_retrieve_temp_keys_data()
            return True
        return False

    async def async_retrieve_device_data(self) -> bool:
        """Request and parse the user's device data."""
        user_conf_data = await self.async_user_conf()
        if user_conf_data is not None:
            self._data.parse_userconf_data(user_conf_data) # type: ignore
            return True
        return False

    async def async_retrieve_user_data_with_tokens(self, auth_token, token) -> bool:
        """Retrieve user devices and temp keys data with an alternate token string."""
        self._data.auth_token = auth_token
        self._data.token = token
        return await self.async_retrieve_user_data()

    async def async_refresh_token(self) -> bool:
        """Refresh the authentication tokens using the refresh token."""
        if not self._data.refresh_token:
            LOGGER.error("❌ No refresh token available for token refresh")
            return False
        
        LOGGER.debug("📡 Refreshing authentication tokens...")
        url = f"https://gate.{self._data.subdomain}.akuvox.com:{REST_SERVER_PORT}/{API_REFRESH_TOKEN}"
        
        headers = {
            "x-auth-token": self._data.token,
            "user-agent": "VBell/7.20.5 (iPhone; iOS 26.1; Scale/2.00)",
            "content-type": "application/json",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "api-version": "6.8",
        }
        
        data = json.dumps({
            "refresh_token": self._data.refresh_token
        })

        LOGGER.debug("🔸 Sending refresh token request to %s", url)
        LOGGER.debug("🔸 Headers being sent:")
        for k, v in headers.items():
            LOGGER.debug("   %s: %s", k, v)
        LOGGER.debug("🔸 Request body: %s", data)

        json_data = await self._async_api_wrapper(
            method="post",
            url=url,
            headers=headers,
            data=data
        )

        LOGGER.debug("🔸 json_data (raw): %s", json_data)
        
        if json_data is not None:
            if "err_code" in json_data and json_data["err_code"] == "0":
                if "datas" in json_data:
                    token_data = json_data["datas"]
                    
                    # Update tokens
                    old_token = self._data.token[:10] + "..." if len(self._data.token) > 10 else self._data.token
                    old_refresh_token = self._data.refresh_token[:10] + "..." if len(self._data.refresh_token) > 10 else self._data.refresh_token
                    
                    self._data.token = token_data.get("token", self._data.token)
                    self._data.refresh_token = token_data.get("refresh_token", self._data.refresh_token)
                    
                    new_token = self._data.token[:10] + "..." if len(self._data.token) > 10 else self._data.token
                    new_refresh_token = self._data.refresh_token[:10] + "..." if len(self._data.refresh_token) > 10 else self._data.refresh_token
                    
                    LOGGER.debug("✅ Tokens refreshed successfully")
                    LOGGER.debug("   Old token: %s", old_token)
                    LOGGER.debug("   New token: %s", new_token)
                    LOGGER.debug("   Old refresh token: %s", old_refresh_token)
                    LOGGER.debug("   New refresh token: %s", new_refresh_token)
                    
                    # Store updated tokens
                    await self._data.async_set_stored_data_for_key("token", self._data.token)
                    await self._data.async_set_stored_data_for_key("refresh_token", self._data.refresh_token)
                    await self._data.async_set_stored_data_for_key(
                        "last_token_refresh", int(asyncio.get_event_loop().time())
                    )

                    LOGGER.debug("💾 Stored new token pair to persistent storage:")
                    LOGGER.debug("   token = %s", self._data.token)
                    LOGGER.debug("   refresh_token = %s", self._data.refresh_token)

                    # Optional confirmation of saved values
                    confirm_token = await self._data.async_get_stored_data_for_key("token")
                    confirm_refresh = await self._data.async_get_stored_data_for_key("refresh_token")
                    LOGGER.debug("🔍 Confirmed saved tokens in storage: token=%s | refresh_token=%s", confirm_token, confirm_refresh)

                    return True
                
            LOGGER.error("❌ Token refresh failed: %s", json_data.get("message", "Unknown error"))
        else:
            LOGGER.error("❌ Token refresh request failed")
        
        return False

    async def async_user_conf(self):
        """Request the user's configuration data."""
        LOGGER.debug("📡 Retrieving list of user's devices...")
        url = f"https://{self._data.host}/{API_USERCONF}?token={self._data.token}"
        data = {}
        headers = {
            "Host": self._data.host,
            "X-AUTH-TOKEN": self._data.token,
            "Connection": "keep-alive",
            "api-version": USERCONF_API_VERSION,
            "Accept": "*/*",
            "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
            "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
            "x-cloud-lang": "en"
        }
        json_data = await self._async_api_wrapper(method="get", url=url, headers=headers, data=data)

        if json_data is not None:
            LOGGER.debug("✅ User's device list retrieved successfully")
            return json_data

        LOGGER.error("❌ Unable to retrieve user's device list.")
        return None

    def make_opendoor_request(self, name: str, host: str, data: str):
        """Request the user's configuration data."""
        LOGGER.debug("📡 Sending request to open door '%s'...", name)
        LOGGER.debug("Request data = %s", str(data))
        url = f"https://{host}/{API_OPENDOOR}?token={self._data.token}"
        headers = {
            "Host": host,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-AUTH-TOKEN": self._data.token,
            "api-version": OPENDOOR_API_VERSION,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Accept": "*/*",
            "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
            "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
            "Content-Length": "24",
            "x-cloud-lang": "en",
        }
        LOGGER.debug("🔑 Using token for door open: %s", self._data.token)
        response = self.post_request(url=url, headers=headers, data=data)
        json_data = self.process_response(response, url)
        if json_data is not None:
            LOGGER.debug("✅ Door open request sent successfully.")
            return json_data

        LOGGER.error("❌ Request to open door failed.")
        return None

    async def async_retrieve_temp_keys_data(self) -> bool:
        """Request and parse the user's temporary keys."""
        json_data = await self.async_get_temp_key_list()
        if json_data is not None:
            self._data.parse_temp_keys_data(json_data)
            return True
        return False

    async def async_get_temp_key_list(self):
        """Request the user's configuration data."""
        LOGGER.debug("📡 Retrieving list of user's temporary keys...")
        host = self.get_activities_host()
        subdomain = self._data.subdomain # await self._data.async_get_stored_data_for_key("subdomain")
        url = f"https://{host}/{API_GET_PERSONAL_TEMP_KEY_LIST}"
        data = {}
        headers = {
            "x-cloud-version": "6.4",
            "accept": "application/json, text/plain, */*",
            "sec-fetch-site": "same-origin",
            "accept-language": "en-AU,en;q=0.9",
            "sec-fetch-mode": "cors",
            "x-cloud-lang": "en",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) SmartPlus/6.2",
            "referer": f"https://{subdomain}.akuvox.com/smartplus/TmpKey.html?TOKEN={self._data.token}&USERTYPE=20&VERSION=6.6",
            "x-auth-token": self._data.token,
            "sec-fetch-dest": "empty"
        }

        json_data = await self._async_api_wrapper(method="get", url=url, headers=headers, data=data)

        if json_data is not None:
            LOGGER.debug("✅ User's temporary keys list retrieved successfully")
            return json_data

        LOGGER.error("❌ Unable to retrieve user's temporary key list.")
        return None

    async def async_start_polling_personal_door_log(self):
        """Poll the server contineously for the latest personal door log."""
        # Make sure only 1 instance of the door log polling is running
        self.hass.async_create_task(self.async_retrieve_personal_door_log())

    async def async_retrieve_personal_door_log(self) -> bool:
        """Request and parse the user's door log every 2 seconds."""
        while True:
            # Get the latest pesonal door log
            json_data = await self.async_get_personal_door_log()
            if json_data is not None:
                new_door_log = await self._data.async_parse_personal_door_log(json_data)
                if new_door_log is not None:
                    # Fire HA event
                    LOGGER.debug("🚪 New door open event occurred. Firing akuvox_door_update event")
                    event_name = "akuvox_door_update"
                    self.hass.bus.async_fire(event_name, new_door_log)
            await asyncio.sleep(2)  # Wait for 2 seconds before calling again

    async def async_get_personal_door_log(self):
        """Request the user's personal door log data."""
        # LOGGER.debug("📡 Retrieving list of user's personal door log...")
        host = self.get_activities_host()
        url = f"https://{host}/{API_GET_PERSONAL_DOOR_LOG}"
        data = {}
        headers = {
            "x-cloud-version": "6.4",
            "accept": "application/json, text/plain, */*",
            "sec-fetch-site": "same-origin",
            "accept-language": "en-AU,en;q=0.9",
            "sec-fetch-mode": "cors",
            "x-cloud-lang": "en",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) SmartPlus/6.2",
            "referer": f"https://{self._data.subdomain}.akuvox.com/smartplus/Activities.html?TOKEN={self._data.token}",
            "x-auth-token": self._data.token,
            "sec-fetch-dest": "empty"
        }

        json_data: list = await self._async_api_wrapper(method="get",
                                                        url=url,
                                                        headers=headers,
                                                        data=data) # type: ignore

        # Response empty, try changing app type "single" <--> "community"
        if json_data is not None and len(json_data) == 0:
            self.switch_activities_host()
            host = self.get_activities_host()
            url = f"https://{host}/{API_GET_PERSONAL_DOOR_LOG}"
            json_data = await self._async_api_wrapper(method="get",
                                                      url=url,
                                                      headers=headers,
                                                      data=data) # type: ignore

        if json_data is not None and len(json_data) > 0:
            return json_data

        # DEBUG block before error log
        if json_data is None:
            LOGGER.debug("🧩 personal_door_log debug: Response is None. Token=%s | URL=%s", self._data.token, url)
        else:
            LOGGER.debug("🧩 personal_door_log debug: Received response = %s", json_data)

        LOGGER.error("❌ Unable to retrieve user's personal door log")
        return None

    ###################
    # Request Methods #
    ###################

    async def _async_api_wrapper(
        self,
        method: str,
        url: str,
        data,
        headers: dict | None = None,
    ):
        """Get information from the API."""
        try:
            async with async_timeout.timeout(10):
                func = self.post_request if method == "post" else self.get_request
                subdomain = self._data.subdomain
                url = url.replace("subdomain.", f"{subdomain}.")
                if not url.endswith(API_GET_PERSONAL_DOOR_LOG):
                    LOGGER.debug("⏳ Sending request to %s", url)
                response = await self.hass.async_add_executor_job(func, url, headers, data, 10)
                return self.process_response(response, url)

        except asyncio.TimeoutError as exception:
            # Fix for accounts which use the "single" endpoint instead of "community"
            app_type_1 = "community"
            app_type_2 = "single"
            if f"app/{app_type_1}/" in url:
                LOGGER.warning("Request 'app/%s' API %s request timed out: %s - Retry using '%s'",
                               app_type_1,
                               method,
                               url,
                               app_type_2)
                self._data.app_type = app_type_2
                url = url.replace("app/"+app_type_1+"/", "app/"+app_type_2+"/")
                return await self._async_api_wrapper(method, url, data, headers)
            if f"app/{app_type_2}/" in url:
                LOGGER.error("Timeout occured for 'app/%s' API %s request: %s",
                             app_type_2,
                             method,
                             url)
                self._data.app_type = app_type_1
            raise AkuvoxApiClientCommunicationError(
                f"Timeout error fetching information: {exception}",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise AkuvoxApiClientCommunicationError(
                f"Error fetching information: {exception}",
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            raise AkuvoxApiClientError(
                f"Something really wrong happened! {exception}. URL = {url}"
            ) from exception
        return None

    def process_response(self, response, url):
        """Process response and return dict with data."""
        if response.status_code == 200:
            # Assuming the response is valid JSON, parse it
            try:
                json_data = response.json()

                # Standard requests
                if "result" in json_data and json_data["result"] == 0:
                    if "datas" in json_data:
                        return json_data["datas"]
                    return json_data

                # Temp key requests
                if "code" in json_data:
                    if json_data["code"] == 0:
                        if "data" in json_data:
                            return json_data["data"]
                        return json_data
                    return []
                
                # Refresh token or newer API pattern
                if "err_code" in json_data and str(json_data["err_code"]) == "0":
                    return json_data
                LOGGER.warning("🤨 Response: %s", str(json_data))
                
            except Exception as error:
                LOGGER.error("❌ Error occurred when parsing JSON: %s\nRequest: %s",
                             error,
                             url)
        else:
            LOGGER.debug("❌ Error: HTTP status code = %s for request to %s",
                         response.status_code,
                         url)
        return None

    async def async_make_get_request(self, url, headers, data=None):
        """Make an HTTP get request."""
        return await self.async_make_request("get", url, headers, data)

    async def async_make_post_request(self, url, headers, data=None):
        """Make an HTTP post request."""
        return await self.async_make_request("post", url, headers, data)

    async def async_make_request(self, request_type, url, headers, data=None):
        """Make an HTTP request."""
        func = self._session.post if request_type == "post" else self._session.get

        response = await func(url=url, headers=headers, data=data)
        if response is not None:
            if response.status == 200:
                # Assuming the response is valid JSON, parse it
                try:
                    json_data = response.json()
                    return json_data
                except Exception as error:
                    LOGGER.warning(
                        "❌ Error occurred when parsing JSON: %s", error)
            else:
                LOGGER.debug("❌ Error: HTTP status code %s",
                             response.status)
                return None

    def post_request(self, url, headers, data="", timeout=10):
        """Make a synchronous post request."""
        response: requests.Response = requests.post(url,
                                                    headers=headers,
                                                    data=data,
                                                    timeout=timeout)
        return response

    def get_request(self, url, headers, data, timeout=10):
        """Make a synchronous post request."""
        response: requests.Response = requests.get(url,
                                                   headers=headers,
                                                   data=data,
                                                   timeout=timeout)
        return response

    ###########
    # Getters #
    ###########

    def get_title(self) -> str:
        """Title of Akuvox account."""
        return self._data.project_name

    def get_devices_json(self) -> dict:
        """Device data dictionary."""
        return self._data.get_device_data()

    def get_obfuscated_phone_number(self, phone_number):
        """Obfuscate the user's phone number for API requests."""
        if (phone_number is None or len(phone_number) == 0):
            LOGGER.error("No phone number provided for obfuscation")
        # Mask phone number
        try:
            num_str = str(phone_number)
        except Exception as error:
            LOGGER.error("Unable to get obfuscated phone number from %s: %s",
                         str(phone_number),
                         str(error))
            return False
        transformed_str = ""
        # Iterate through each digit in the input number
        for digit_char in num_str:
            digit = int(digit_char)
            # Add 3 to the digit and take the result modulo 10
            transformed_digit = (digit + 3) % 10
            transformed_str += str(transformed_digit)
        return int(transformed_str)

    def get_activities_host(self):
        """Get the host address string for activities API requests."""
        if self._data.app_type == "single":
            return API_APP_HOST + "single"
        return API_APP_HOST + "community"

    def switch_activities_host(self):
        """Switch the activities host from single <--> community."""
        if self._data.app_type == "single":
            LOGGER.debug("Switching API address from 'single' to 'community'")
            self._data.app_type = "community"
        else:
            self._data.app_type = "single"
            LOGGER.debug("Switching API address from 'community' to 'single'")

    def update_data(self, key, value):
        """Update the data model."""
        self._data.subdomain = value if key == "subdomain" else self._data.subdomain
        self._data.auth_token = value if key == "auth_token" else self._data.auth_token
        self._data.token = value if key == "token" else self._data.token
        self._data.refresh_token = value if key == "refresh_token" else self._data.refresh_token
        self._data.wait_for_image_url = value if key == "wait_for_image_url" else self._data.wait_for_image_url

    async def async_check_and_refresh_tokens(self) -> bool:
        """Check if tokens need refresh and refresh if necessary (every 6 days)."""
        last_refresh = await self._data.async_get_stored_data_for_key("last_token_refresh")
        current_time = int(asyncio.get_event_loop().time())
        
        # Refresh tokens every N days (configurable) - 1 day safety buffer before 7-day expiry
        refresh_interval = TOKEN_REFRESH_INTERVAL_DAYS * 24 * 60 * 60  # Convert days to seconds
        
        if last_refresh is None or (current_time - last_refresh) >= refresh_interval:
            LOGGER.debug("🔄 Token refresh needed (last refresh: %s)", 
                        last_refresh if last_refresh else "never")
            return await self.async_refresh_token()
        
        time_until_refresh = refresh_interval - (current_time - last_refresh)
        days_until_refresh = time_until_refresh // (24 * 60 * 60)
        LOGGER.debug("✅ Tokens are fresh (refresh in %d days)", days_until_refresh)
        return True
