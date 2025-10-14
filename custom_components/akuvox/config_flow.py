"""Adds config flow for Akuvox."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import voluptuous as vol
from .api import AkuvoxApiClient
from .coordinator import AkuvoxDataUpdateCoordinator

from .const import (
    DOMAIN,
    DEFAULT_TOKEN,
    DEFAULT_APP_TOKEN,
    LOGGER,
    LOCATIONS_DICT,
    COUNTRY_PHONE,
    SUBDOMAINS_LIST,
)
from .helpers import AkuvoxHelpers

helpers = AkuvoxHelpers()

class AkuvoxFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Akuvox."""

    VERSION = 1
    data: dict = {}
    rest_server_data: dict = {}
    akuvox_api_client: AkuvoxApiClient = None  # type: ignore

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AkuvoxOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Step 0: User selects sign-in method."""

        # Initialize the API client
        if self.akuvox_api_client is None:
            coordinator: AkuvoxDataUpdateCoordinator = None # type: ignore
            if DOMAIN in self.hass.data:
                for _key, value in self.hass.data[DOMAIN].items():
                    coordinator = value
            if coordinator:
                self.akuvox_api_client = coordinator.client
            else:
                self.akuvox_api_client = AkuvoxApiClient(
                    session=async_get_clientsession(self.hass),
                    hass=self.hass,
                    entry=None)


        return self.async_show_menu(
            step_id="user",
            menu_options=["sms_sign_in_warning", "app_tokens_sign_in"],
            description_placeholders=user_input,
        )

    async def async_step_sms_sign_in_warning(self, user_input=None):
        """Step 1a: Warning before continuing with login via SMS Verification."""
        errors = {}
        sms_sign_in = "Continue sign-in via SMS Verification"
        app_tokens_sign_in = "Sign-in via app tokens"
        data_schema = {
            "warning_option_selection": selector.selector({
                "select": {
                    "options": [sms_sign_in, app_tokens_sign_in],
                }
            })
        }
        if user_input is not None:
            if "warning_option_selection" in user_input:
                selection = user_input["warning_option_selection"]
                if selection == sms_sign_in:
                    return self.async_show_form(
                        step_id="sms_sign_in",
                        data_schema=vol.Schema(self.get_sms_sign_in_schema(user_input)),
                        description_placeholders=user_input,
                        last_step=False,
                        errors=None
                    )
                if selection == app_tokens_sign_in:
                    return self.async_show_form(
                        step_id="app_tokens_sign_in",
                        data_schema=vol.Schema(self.get_app_tokens_sign_in_schema(user_input)),
                        description_placeholders=user_input,
                        last_step=False,
                        errors=None
                    )
                errors["base"] = "Please choose a sign-in option."
            else:
                errors["base"] = "Please choose a valid sign-in option."

        return self.async_show_form(
            step_id="sms_sign_in_warning",
            data_schema=vol.Schema(data_schema),
            description_placeholders=user_input,
            last_step=False,
            errors=errors
        )


    async def async_step_sms_sign_in(self, user_input=None):
        """Step 1b: User enters their mobile phone country code and number.

        Args:
            user_input (dict): User-provided input data.

        Returns:
            dict: A dictionary representing the next step or an entry creation.

        """

        data_schema = self.get_sms_sign_in_schema(user_input)

        if user_input is not None:
            country_code = helpers.get_country_phone_code_from_name(user_input.get("country_code"))
            phone_number = user_input.get(
                "phone_number", "").replace("-", "").replace(" ", "")
            subdomain: str = user_input.get("subdomain", "Default")
            subdomain = subdomain if subdomain != "Default" else helpers.get_subdomain_from_country_code(country_code)

            location_dict = helpers.get_location_dict(country_code)
            LOGGER.debug("User will use the API subdomain '%s' for %s", subdomain, location_dict.get("country"))

            self.data = {
                "full_phone_number": f"(+{country_code}) {phone_number}",
                "country_code": country_code,
                "phone_number": phone_number,
                "subdomain": subdomain
            }

            if len(country_code) > 0 and len(phone_number) > 0: # type: ignore
                # Request SMS code for login
                request_sms_code = await self.akuvox_api_client.async_send_sms(self.hass, country_code, phone_number, subdomain)
                if request_sms_code:
                    return await self.async_step_verify_sms_code()
                else:
                    return self.async_show_form(
                        step_id="sms_sign_in",
                        data_schema=vol.Schema(data_schema),
                        description_placeholders=user_input,
                        last_step=False,
                        errors={
                            "base": "SMS code request failed. Check your phone number."
                        }
                    )

            return self.async_show_form(
                step_id="sms_sign_in",
                data_schema=vol.Schema(data_schema),
                description_placeholders=user_input,
                last_step=False,
                errors={
                    "base": "Please enter a valid country code and phone number."
                }
            )

        return self.async_show_form(
            step_id="sms_sign_in",
            data_schema=vol.Schema(data_schema),
            description_placeholders=user_input,
            last_step=False,
        )


    async def async_step_app_tokens_sign_in(self, user_input=None):
        """Step 1c: User enters app tokens and phone number to sign in."""
        data_schema = self.get_app_tokens_sign_in_schema(user_input) # type: ignore
        if user_input is not None:
            country_code: str = helpers.get_country_phone_code_from_name(user_input.get("country_code")) # type: ignore
            phone_number: str = user_input.get(
                "phone_number", "").replace("-", "").replace(" ", "")
            token: str = user_input.get("token", "")
            auth_token: str = user_input.get("auth_token", "")
            refresh_token: str = user_input.get("refresh_token", "")
            subdomain: str = user_input.get("subdomain", "Default")
            subdomain = subdomain if subdomain != "Default" else helpers.get_subdomain_from_country_code(country_code)

            self.data = {
                "full_phone_number": f"(+{country_code}) {phone_number}",
                "country_code": country_code,
                "phone_number": phone_number,
                "token": token,
                "auth_token": auth_token,
                "refresh_token": refresh_token,
                "subdomain": subdomain
            }

            # Perform login via auth_token, token and phone number
            if all(len(value) > 0 for value in (country_code, phone_number, token, auth_token)):
                # Retrieve servers_list data.
                login_successful = await self.akuvox_api_client.async_make_servers_list_request(
                    hass=self.hass,
                    auth_token=auth_token,
                    token=token,
                    country_code=country_code,
                    phone_number=phone_number,
                    subdomain=subdomain)
                if login_successful is True:
                    # Retrieve connected device data
                    await self.akuvox_api_client.async_retrieve_user_data()
                    devices_json = self.akuvox_api_client.get_devices_json()
                    self.data.update(devices_json)

                    ################################
                    ### Create integration entry ###
                    ################################
                    return self.async_create_entry(
                        title=self.akuvox_api_client.get_title(),
                        data=self.data
                    )
                else:
                    LOGGER.error("❌ Unable to retrieve user data. Check your tokens.")

                return self.async_show_form(
                    step_id="app_tokens_sign_in",
                    data_schema=vol.Schema(self.get_app_tokens_sign_in_schema(user_input)),
                    description_placeholders=user_input,
                    last_step=True,
                    errors={
                        "base": "Sign in failed. Please check the values entered and try again."
                    }
                )

            return self.async_show_form(
                step_id="app_tokens_sign_in",
                data_schema=vol.Schema(data_schema),
                description_placeholders=user_input,
                last_step=True,
                errors={
                    "base": "Please check the values enterted and try again."
                }
            )

        return self.async_show_form(
            step_id="app_tokens_sign_in",
            data_schema=vol.Schema(data_schema),
            description_placeholders=user_input,
            last_step=True,
        )

    async def async_step_verify_sms_code(self, user_input=None):
        """Step 2: User enters the SMS code received on their phone for verifiation.

        Args:
            user_input (dict): User-provided input data.

        Returns:
            dict: A dictionary representing the next step or an entry creation.

        """

        data_schema = {
            vol.Required(
                "sms_code",
                msg=None,
                description="Enter the code from the SMS you received on your device."): str,
        }

        if user_input is not None and user_input:
            sms_code = user_input.get("sms_code")
            country_code = self.data["country_code"]
            phone_number = self.data["phone_number"]

            # Validate SMS code
            sign_in_response = await self.akuvox_api_client.async_sms_sign_in(
                phone_number,
                country_code,
                sms_code)
            if sign_in_response is True:

                devices_json = self.akuvox_api_client.get_devices_json()
                self.data.update(devices_json)

                ################################
                ### Create integration entry ###
                ################################
                return self.async_create_entry(
                    title=self.akuvox_api_client.get_title(),
                    data=self.data
                )

            user_input = None
            return self.async_show_form(
                step_id="verify_sms_code",
                data_schema=vol.Schema(data_schema),
                description_placeholders=user_input,
                last_step=True,
                errors={
                    "sms_code": "Invalid SMS code. Please enter the correct code."
                }
            )

        return self.async_show_form(
            step_id="verify_sms_code",
            data_schema=vol.Schema(data_schema),
            description_placeholders=user_input,
            last_step=True
        )

    def get_sms_sign_in_schema(self, user_input):
        """Get the schema for sms_sign_in step."""
        user_input = user_input or {}

        # List of countries
        default_country_name_code = helpers.find_country_name_code(str(COUNTRY_PHONE.get(self.hass.config.country,"")))
        default_country_name = LOCATIONS_DICT.get(default_country_name_code, {}).get("country") # type: ignore
        country_names_list:list = helpers.get_country_names_list()

        return {
            vol.Required("country_code",
                         default=default_country_name,
                         description="Your phone's international calling code prefix"):
                         selector.SelectSelector(
                             selector.SelectSelectorConfig(
                                 options=country_names_list,
                                 mode=selector.SelectSelectorMode.DROPDOWN,
                                 custom_value=False),
                                 ),
            vol.Required(
                "phone_number",
                msg=None,
                default=user_input.get("phone_number"),  # type: ignore
                description="Your phone number"): str,
            vol.Optional("subdomain",
                default="Default", # type: ignore
                description="Manually set the regional API subdomain"):
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SUBDOMAINS_LIST,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True),
                        )
        }

    def get_app_tokens_sign_in_schema(self, user_input: dict = {}):
        """Get the schema for app_tokens_sign_in step."""
        user_input = user_input or {}

        default_country_name_code = helpers.find_country_name_code(str(COUNTRY_PHONE.get(self.hass.config.country,"")))
        default_country_name = LOCATIONS_DICT.get(default_country_name_code, {}).get("country") # type: ignore
        country_names_list:list = helpers.get_country_names_list()

        return {
            vol.Required("country_code",
                         default=default_country_name,
                         description="Your phone's international calling code prefix"):
                         selector.SelectSelector(
                             selector.SelectSelectorConfig(
                                 options=country_names_list,
                                 mode=selector.SelectSelectorMode.DROPDOWN,
                                 custom_value=False),
                                 ),
            vol.Required(
                "phone_number",
                msg=None,
                default=user_input.get("phone_number"),  # type: ignore
                description="Your phone number"): str,
            vol.Required(
                "auth_token",
                msg=None,
                default=user_input.get("auth_token", DEFAULT_APP_TOKEN),  # type: ignore
                description="Your SmartPlus account's auth_token string"): str,
            vol.Required(
                "token",
                msg=None,
                default=user_input.get("token", DEFAULT_TOKEN),  # type: ignore
                description="Your SmartPlus account's token string"): str,
            vol.Optional(
                "refresh_token",
                msg=None,
                default=user_input.get("refresh_token", ""),  # type: ignore
                description="Your SmartPlus account's refresh_token string (optional)"): str,
            vol.Optional("subdomain",
                         default="Default", # type: ignore
                         description="Manually set the regional API subdomain"):
                         selector.SelectSelector(
                             selector.SelectSelectorConfig(
                                 options=SUBDOMAINS_LIST,
                                 mode=selector.SelectSelectorMode.DROPDOWN,
                                 custom_value=True),
                                 )
        }

class AkuvoxOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Akuvox integration."""

    akuvox_api_client: AkuvoxApiClient = None  # type: ignore

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Initialize the options flow."""
        # Get current config and options
        config_options = dict(self.config_entry.options)
        config_data = dict(self.config_entry.data)

        event_screenshot_options = {
            "asap": "Receive events once generated, without waiting for camera screenshot URLs.",
            "wait": "Wait for camera screenshot URLs to become available before triggering the event (typically adds a delay of 0-3 seconds)."
        }

        # Updated logic for default_country_name to handle both country names and numeric codes
        stored_country = config_options.get("country_code") or config_data.get("country_code")

        # Determine what to display
        if stored_country in [v.get("country") for v in LOCATIONS_DICT.values()]:
            # It’s already a full country name (e.g., "Singapore")
            default_country_name = stored_country
        else:
            # Convert from numeric code or ISO format
            default_country_name_code = helpers.find_country_name_code(str(stored_country or self.hass.config.country))
            default_country_name = LOCATIONS_DICT.get(default_country_name_code, {}).get("country", "")

        # Subdomain and country names list
        default_subdomain = config_options.get("subdomain") or config_data.get("subdomain") or helpers.get_subdomain_from_country_code(stored_country or self.hass.config.country)
        subdomain_list = list(SUBDOMAINS_LIST)
        if "Default" in subdomain_list:
            subdomain_list.remove("Default")

        country_names_list = [v.get("country") for k, v in LOCATIONS_DICT.items()]

        # Build schema
        options_schema = vol.Schema({
            vol.Optional("country_code", default=default_country_name):
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=country_names_list,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=False
                    )
                ),
            vol.Optional("phone_number", default=self.get_data_key_value("phone_number", "")): str,
            vol.Optional("auth_token", default=self.get_data_key_value("auth_token", "")): str,
            vol.Optional("refresh_token", default=self.get_data_key_value("refresh_token", "")): str,
            vol.Optional("token", default=self.get_data_key_value("token", "")): str,
            vol.Optional("subdomain", default=default_subdomain):
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=subdomain_list,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True
                    )
                ),
            vol.Required("event_screenshot_options", default=self.get_data_key_value("event_screenshot_options", "asap")):
                vol.In(event_screenshot_options),
        })

        # Show form
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=options_schema,
                description_placeholders=user_input,
                last_step=True
            )

        # Validate tokens
        api_client: AkuvoxApiClient = None
        for _k, v in self.hass.data[DOMAIN].items():
            coordinator = v
            api_client = coordinator.client
        if api_client is not None:
            api_client._data.subdomain = user_input.get("subdomain", default_subdomain)
            api_client._data.auth_token = user_input.get("auth_token", "")
            api_client._data.token = user_input.get("token", "")
            api_client._data.phone_number = user_input.get("phone_number", "")
            try:
                valid = await api_client.async_retrieve_user_data_with_tokens(
                    user_input.get("auth_token", ""),
                    user_input.get("token", "")
                )
                if not valid:
                    errors = {"token": "Unable to validate tokens. Check your auth_token and token."}
                    return self.async_show_form(
                        step_id="init",
                        data_schema=options_schema,
                        errors=errors
                    )
            except Exception as e:
                errors = {"token": f"Error validating tokens: {e}"}
                return self.async_show_form(
                    step_id="init",
                    data_schema=options_schema,
                    errors=errors
                )

        # All good, create entry
        return self.async_create_entry(
            data=user_input,
            title=""
        )

    def get_data_key_value(self, key, placeholder=None):
        """Get the value for a given key. Options flow 1st, Config flow 2nd."""
        dicts = [dict(self.config_entry.options), dict(self.config_entry.data)]
        for p_dict in dicts:
            if key in p_dict:
                return p_dict[key]
        return placeholder
