# How to Get Your First Refresh Token

## Option 1: Automatic Capture (Recommended)

The easiest way is to let the integration capture the refresh token automatically during setup:

### For New Users
1. **Delete existing integration** (if you have one) from Home Assistant
2. **Re-add the integration** using SMS verification
3. **Check the logs** - you should see: `✅ Refresh token captured and stored from SMS login`
4. **Done!** The integration will now automatically refresh tokens every 6 days (1 day before they expire)

### For Existing Users with App Tokens
1. Go to **Settings > Devices & Services > Akuvox**
2. Click **Configure** on your Akuvox integration
3. **Leave the refresh_token field empty** initially
4. Save and **check the logs** for: `✅ Refresh token captured and stored from servers_list`

## Option 2: Manual Capture (If Automatic Doesn't Work)

If the automatic capture doesn't work, you'll need to capture the refresh token manually:

### Prerequisites
- Computer with network monitoring tools
- SmartPlus mobile app
- WiFi network access

### Steps

1. **Install mitmproxy**:
   ```bash
   pip install mitmproxy
   ```

2. **Start mitmproxy**:
   ```bash
   mitmweb --listen-port 8080 --web-port 8081
   ```

3. **Configure your phone**:
   - Connect phone to same WiFi as computer
   - Set phone's WiFi proxy to your computer's IP:8080
   - Install mitmproxy certificate on phone (follow mitmproxy docs)

4. **Capture login**:
   - **Log out** of SmartPlus app completely
   - **Clear app cache/data** (Android) or delete/reinstall app (iOS)
   - **Log back in** to SmartPlus
   - Watch mitmproxy web interface at http://localhost:8081

5. **Find the tokens**:
   Look for requests to `gate.*.akuvox.com:8600` containing:
   - `sms_login` response
   - `servers_list` response
   
   The JSON response should contain:
   ```json
   {
     "token": "your_token_here",
     "refresh_token": "your_refresh_token_here",
     "auth_token": "your_auth_token_here"
   }
   ```

6. **Add to Home Assistant**:
   - Go to Akuvox integration settings
   - Add both `token` and `refresh_token` values
   - Save configuration

## Verification

Check your Home Assistant logs for these messages:

### Success Messages
- `✅ Refresh token captured and stored from SMS login`
- `✅ Refresh token captured and stored from servers_list` 
- `📱 Loaded refresh token from storage`
- `✅ Tokens are fresh (refresh in X days)`

### Warning Messages
- `⚠️ No refresh token received from SMS login response`
- `❌ No refresh token available for token refresh`

## Using the Services

Once you have a refresh token, you can use these services:

### Manual Token Update
```yaml
service: akuvox.update_tokens
data:
  entry_id: "your_entry_id_here"  # Find in logs or developer tools
  token: "new_token"
  refresh_token: "new_refresh_token"  # Optional
```

### Automatic Refresh
```yaml
service: akuvox.refresh_tokens  
data:
  entry_id: "your_entry_id_here"
```

## Troubleshooting

### "No refresh token available"
- The Akuvox API might not always return refresh tokens
- Try the SMS login method instead of app tokens
- Capture manually using mitmproxy

### Refresh fails after 7 days
- Check if your refresh token is still valid
- Re-login to SmartPlus and capture new tokens
- Some accounts may not support refresh tokens

### Finding your Entry ID
Check Home Assistant logs for messages containing your entry ID, or use Developer Tools > States to find entities starting with your integration name.