# Token Refresh Implementation

This document describes the token refresh functionality implemented for the Akuvox Home Assistant integration.

## Overview

The implementation adds automatic token refresh capability that calls the Akuvox API every 7 days to refresh authentication tokens, preventing the need for manual token updates.

## Features

### 1. Automatic Token Refresh
- **Frequency**: Automatically refreshes tokens every 6 days (518400 seconds) - provides 1 day safety buffer before 7-day expiry
- **API Endpoint**: `https://gate.ecloud.akuvox.com:8600/refresh_token`
- **Method**: POST with JSON payload containing the refresh token
- **Headers**: Uses proper user-agent and auth headers as specified

### 2. Manual Token Update Services
Two new Home Assistant services have been added:

#### `akuvox.update_tokens`
Manually update authentication tokens.

**Parameters:**
- `entry_id` (required): The config entry ID of the Akuvox integration
- `token` (required): The new authentication token
- `refresh_token` (optional): The new refresh token

**Example usage:**
```yaml
service: akuvox.update_tokens
data:
  entry_id: "01234567890abcdef"
  token: "your_new_token_here"
  refresh_token: "your_new_refresh_token_here"
```

#### `akuvox.refresh_tokens`
Refresh tokens using the stored refresh token.

**Parameters:**
- `entry_id` (required): The config entry ID of the Akuvox integration

**Example usage:**
```yaml
service: akuvox.refresh_tokens
data:
  entry_id: "01234567890abcdef"
```

## Implementation Details

### Files Modified

1. **`const.py`**: Added `API_REFRESH_TOKEN = "refresh_token"` constant
2. **`data.py`**: Added refresh token storage and handling
3. **`api.py`**: Added token refresh logic and automatic refresh checking
4. **`config_flow.py`**: Added refresh token field to configuration forms
5. **`__init__.py`**: Added service registration and handlers
6. **`services.yaml`**: New file documenting the available services

### Key Methods Added

- `async_refresh_token()`: Performs the actual token refresh API call
- `async_check_and_refresh_tokens()`: Checks if refresh is needed and performs it
- `async_update_tokens_service()`: Service handler for manual token updates
- `async_refresh_tokens_service()`: Service handler for refresh token calls

### Token Storage

Tokens are stored using Home Assistant's storage system:
- `token`: The current authentication token
- `refresh_token`: The refresh token for automatic renewals
- `last_token_refresh`: Timestamp of the last successful refresh

### Integration Flow

1. During API initialization, the system checks if tokens need refresh
2. If 6 days have passed since last refresh, automatic refresh is triggered (1 day before expiry)
3. On successful refresh, new tokens are stored and logged
4. Services allow manual token management when needed

## Usage Instructions

### Getting Refresh Tokens

The refresh token is automatically captured during the initial login process:

#### Automatic Capture (Recommended)
1. **SMS Login**: When setting up the integration with SMS verification, the refresh token is automatically extracted from the login response and stored
2. **App Token Login**: The refresh token may also be captured from the servers_list API response during initial setup

#### Manual Capture (If Needed)
If automatic capture doesn't work:
1. Use mitmproxy or similar tools to capture SmartPlus app traffic during login
2. Extract both `token` and `refresh_token` from the login response 
3. Add both tokens through the integration's configuration options

#### Verifying Refresh Token Capture
Check the Home Assistant logs for these messages:
- `✅ Refresh token captured and stored from SMS login`
- `✅ Refresh token captured and stored from servers_list`
- `⚠️ No refresh token received from SMS login response` (if not found)

### Monitoring
- Check Home Assistant logs for token refresh status
- Look for messages like "✅ Tokens refreshed successfully" or "🔄 Token refresh needed"
- Failed refreshes will be logged as errors

### Troubleshooting
- If automatic refresh fails, use the manual `refresh_tokens` service
- If refresh token is invalid, use `update_tokens` service with new tokens
- Token refresh requires a valid refresh token to be present

## API Response Format
The refresh token API returns:
```json
{
  "datas": {
    "refresh_token": "new refresh token",
    "token": "new token", 
    "token_valid": "604800"
  },
  "err_code": "0",
  "message": "success"
}
```

## Security Notes
- Tokens are obfuscated in logs (showing only first 3 and last 3 characters)
- Refresh tokens are stored securely using Home Assistant's storage system
- Failed refresh attempts are logged for monitoring