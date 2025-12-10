# Akuvox SmartPlus Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/github/v/release/YOUR_USERNAME/akuvox)
[![Community Forum][forum-shield]][forum]

<img src="https://user-images.githubusercontent.com/1849295/269948645-08c99fe2-253e-49cc-b38b-2a2937c2726d.png" width="100">

Integrate your Akuvox SmartPlus intercom system with Home Assistant. Access door camera feeds, trigger door relays remotely, receive instant notifications with camera snapshots, and manage temporary access keys—all from your Home Assistant dashboard.

**⚠️ Important Note:** This repository is a personal fork of the [original project](https://github.com/nimroddolev/akuvox). It is maintained independently with enhanced features and improvements, and there is no intention to merge changes upstream.

---

## ✨ Features

### 🎥 Door Camera Integration
- Live RTSP camera feeds for all your Akuvox door stations
- Automatic camera entity creation for each intercom device
- Real-time video streaming integration with Home Assistant

### 🚪 Remote Door Control
- Open doors remotely via Home Assistant buttons
- Support for multiple relays per door
- Quick access from dashboards, automations, or mobile app

### 🔔 Smart Event Notifications
- Real-time door events (calls, unlocks, face recognition)
- Automatic camera snapshot capture when events occur
- Intelligent retry mechanism ensures snapshots are included in notifications
- Events fire as `akuvox_door_update` with rich metadata

### 🔑 Temporary Access Key Management
- View all temporary access keys from Home Assistant
- Monitor key expiration and usage
- Track which doors each key can access

### 🔄 Automatic Token Refresh
- Tokens automatically refresh every 6 days
- No manual token management required
- Seamless authentication handling

---

## 🎯 Enhanced Features in This Fork

This fork includes several improvements over the original project:

### 🚀 Performance & Reliability
- **Smart Camera Snapshot Handling**: Intelligent retry mechanism with dynamic wait times (0.5s intervals, up to 5s max) ensures camera snapshots are captured before notifications are sent
- **Duplicate Event Prevention**: Async lock prevents duplicate event processing during concurrent API calls
- **Improved Token Management**: Enhanced token refresh logic with better error handling and logging
- **Better Logging**: Comprehensive debug logs with clear emoji indicators for easier troubleshooting

### 🔧 Technical Improvements
- Token persistence and automatic refresh on Home Assistant restart
- Graceful handling of missing camera URLs with configurable timeouts
- Optimized polling mechanism to reduce API calls
- Better error handling throughout the codebase

---

## 📋 Requirements

- Home Assistant 2023.3.0 or newer
- Akuvox SmartPlus account with registered devices
- Network access to Akuvox cloud services

---

## 🔧 Installation

### Via HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations
   - Click the three dots menu (top right) → Custom repositories
   - Add repository URL: `https://github.com/wh1t35m1th/akuvox`
   - Category: Integration
3. Click "Install" on the Akuvox SmartPlus integration
4. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/wh1t35m1th/akuvox/releases)
2. Extract the `custom_components/akuvox` folder
3. Copy it to your Home Assistant `custom_components` directory
4. Restart Home Assistant

---

## ⚙️ Configuration

### Initial Setup

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for "Akuvox SmartPlus"
4. Choose your sign-in method:

#### Method 1: SMS Verification (Recommended)
- Enter your country and phone number
- Receive and enter the SMS verification code
- ⚠️ **Note**: This will sign you out of the SmartPlus mobile app

#### Method 2: App Tokens (Advanced)
- Allows you to stay signed in on your mobile device
- Requires extracting tokens from the SmartPlus app
- See [Token Extraction Guide](#finding-your-smartplus-account-tokens) below

### Optional Configuration

After setup, you can configure additional options:

- **Token Management**: Update tokens if you re-login on your mobile device
- **Event Behavior**: Choose whether to wait for camera snapshots before firing events
- **Regional Settings**: Manually set API subdomain if auto-detection fails

---

## 📱 Using the Integration

### Door Events & Notifications

The integration fires `akuvox_door_update` events with the following data:

```yaml
trigger.event.data:
  Location: "Front Door"          # Door name
  CaptureType: "Call"              # Event type: Call, SmartPlus Unlock, Face Unlock
  Initiator: "John Smith"          # Person who triggered event
  PicUrl: "https://..."            # Camera snapshot URL
  CaptureTime: "05-12-2025 14:30:15"
  MAC: "0C11052B2C6F"              # Device MAC address
  Relay: "1"                       # Relay number used
```

### Example Automation: Door Ring Notification

```yaml
alias: Front Door Ring Alert
triggers:
  - event_type: akuvox_door_update
    event_data:
      CaptureType: Call
      Location: "Front Door"
    trigger: event
actions:
  - action: notify.mobile_app
    data:
      title: "🔔 Someone at Front Door"
      message: "{{ trigger.event.data.Initiator }} is calling"
      data:
        image: "{{ trigger.event.data.PicUrl }}"
        actions:
          - action: "OPEN_DOOR"
            title: "Open Door"
```

### Example Automation: Open Door from Notification

```yaml
alias: Handle Door Open Action
triggers:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: OPEN_DOOR
actions:
  - action: button.press
    target:
      entity_id: button.front_door_relay_1
```

---

## 🎨 Dashboard Examples

### Camera Card
```yaml
type: picture-glance
title: Front Door Camera
camera_image: camera.front_door
entities:
  - button.front_door_relay_1
```

### Event History Card
```yaml
type: logbook
entities:
  - sensor.front_door_temp_key
hours_to_show: 24
```

---

## 🔑 Finding Your SmartPlus Account Tokens

To use the App Tokens sign-in method and stay logged in on your mobile device:

### Requirements
- Computer with mitmproxy installed
- SmartPlus mobile app
- Both devices on the same WiFi network

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
   - Set WiFi proxy to your computer's IP address, port 8080
   - Install mitmproxy certificate on your phone

4. **Capture tokens**:
   - Log out of SmartPlus app completely
   - Clear app cache/data or reinstall
   - Log back in to SmartPlus
   - Open mitmproxy web interface at `http://localhost:8081`

5. **Find tokens**:
   - Look for requests to `gate.*.akuvox.com:8600`
   - Find `sms_login` or `servers_list` response
   - Extract `token`, `auth_token`, and optionally `refresh_token`

See [REFRESH_TOKEN_GUIDE.md](REFRESH_TOKEN_GUIDE.md) for detailed instructions.

---

## 🔍 Troubleshooting

### Common Issues

**Camera feeds not loading**
- Check that your RTSP port (554) is not blocked by your firewall
- Verify camera passwords in the integration logs
- Try reloading the integration

**Notifications without images**
- Camera snapshots may take 1-3 seconds to generate
- Current configuration waits up to 5 seconds for snapshots
- Adjust timeout in integration options if needed

**Token expired errors**
- Tokens should auto-refresh every 6 days
- If issues persist, manually update tokens in integration options
- Check Home Assistant logs for refresh errors

**Duplicate notifications**
- Ensure automation mode is set to `parallel` or `queued`
- Check for multiple automations triggering on the same event

### Debug Logging

Enable debug logging to troubleshoot issues:

```yaml
logger:
  default: info
  logs:
    custom_components.akuvox: debug
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Original integration by [@nimroddolev](https://github.com/nimroddolev/akuvox)
- Based on the [integration_blueprint](https://github.com/ludeeus/integration_blueprint) template
- Thanks to the Home Assistant community for their support

---

## ⚠️ Disclaimer

This integration is not affiliated with or endorsed by Akuvox. It is a community-contributed project provided as-is without any warranty or guarantee. Use it at your own discretion and responsibility.

---

[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=popout
[forum]: https://community.home-assistant.io/t/akuvox-smartplus-view-door-camera-feeds-open-doors-and-manage-temporary-keys/623187

## 📞 Support

- [Home Assistant Community Forum Thread][forum]
- [GitHub Issues](https://github.com/wh1t35m1th/akuvox/issues)
- [Documentation](https://github.com/wh1t35m1th/akuvox/wiki)

---