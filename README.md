# Akuvox SmartPlus Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/github/v/release/wh1t35m1th/akuvox)

Integrate your Akuvox SmartPlus intercom system with Home Assistant. Access live door camera feeds, trigger door relays remotely, receive instant event notifications with camera snapshots, and monitor temporary access keys — all from your Home Assistant dashboard.

> **Note:** This is a personal fork of the [original project](https://github.com/nimroddolev/akuvox), maintained independently with significant improvements. There is no intention to merge changes upstream.

---

## Features

### Camera Integration
- Live video streaming for all Akuvox door station cameras
- Streams are routed through Home Assistant's built-in **go2rtc** relay for compatibility
- Akuvox RTSP streams use UDP transport; go2rtc handles the protocol negotiation so HA's ffmpeg pipeline works correctly

### Door Control
- Open doors remotely via Home Assistant button entities
- Each door relay appears as a separate button entity
- Usable from dashboards, automations, or the mobile app

### Door Event Notifications
- Real-time door events fired as `akuvox_door_update` on the HA event bus
- Events include: door calls, SmartPlus unlocks, face recognition unlocks
- Snapshots are attached to events (with configurable wait for image availability)
- A **Last Door Event** sensor entity tracks the most recent event with full metadata, and persists across HA restarts

### Temporary Access Keys
- All temporary access keys from your Akuvox account appear as sensor entities
- Shows key status (active/expired), begin/end times, allowed uses, and QR code URL

### Token Management
- Tokens auto-refresh every 6 days (1 day before the 7-day expiry)
- A **Token** diagnostic sensor shows the currently active API token (masked)
- Manual token update available via HA service call or integration reconfiguration

---

## Requirements

- Home Assistant 2023.3.0 or newer (go2rtc must be enabled — it is included by default in recent HA versions)
- Akuvox SmartPlus account with registered devices
- Network access to Akuvox cloud services

---

## Installation

### Via HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Go to **HACS → Integrations → ⋮ → Custom repositories**
3. Add repository URL: `https://github.com/wh1t35m1th/akuvox`, category: **Integration**
4. Click **Install** on the Akuvox SmartPlus integration
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/wh1t35m1th/akuvox/releases)
2. Copy the `custom_components/akuvox` folder to your HA `custom_components` directory
3. Restart Home Assistant

---

## Configuration

### Initial Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Akuvox SmartPlus**
3. Choose a sign-in method:

#### Method 1: SMS Verification (Recommended)
- Enter your country and phone number
- Enter the SMS verification code sent to your phone
- **Note:** This will sign you out of the SmartPlus mobile app

#### Method 2: App Tokens (Advanced)
- Lets you stay signed in on your mobile device simultaneously
- Requires extracting tokens from the SmartPlus app using a proxy tool (e.g. mitmproxy)
- See [REFRESH_TOKEN_GUIDE.md](REFRESH_TOKEN_GUIDE.md) for extraction steps

---

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `camera.<door_name>` | Camera | Live RTSP stream via go2rtc |
| `button.<door_name>_relay_<n>` | Button | Open a door relay |
| `sensor.<key_description>_<id>` | Sensor | Temporary access key status |
| `sensor.akuvox_last_door_event` | Sensor | Most recent door event timestamp and metadata |
| `sensor.akuvox_token` | Sensor (diagnostic) | Currently active API token (masked) |

---

## Door Events

The integration fires `akuvox_door_update` events on the HA event bus:

```yaml
trigger.event.data:
  Location: "Front Door"               # Door name
  CaptureType: "Call"                  # Call / SmartPlus Unlock / Face Unlock
  Initiator: "John Smith"              # Person who triggered the event
  PicUrl: "https://..."                # Camera snapshot URL
  CaptureTime: "05-12-2025 14:30:15"  # Event timestamp
  MAC: "0C11052B2C6F"                  # Device MAC address
  Relay: "1"                           # Relay number used
```

The `sensor.akuvox_last_door_event` entity exposes these same fields as attributes and pre-populates on HA restart from the last stored event.

---

## Example Automations

### Door Ring Notification

```yaml
alias: Front Door Ring Alert
triggers:
  - trigger: event
    event_type: akuvox_door_update
    event_data:
      CaptureType: Call
      Location: "Front Door"
actions:
  - action: notify.mobile_app
    data:
      title: "Someone at Front Door"
      message: "{{ trigger.event.data.Initiator }} is calling"
      data:
        image: "{{ trigger.event.data.PicUrl }}"
        actions:
          - action: OPEN_DOOR
            title: "Open Door"
```

### Open Door from Notification

```yaml
alias: Handle Door Open Action
triggers:
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: OPEN_DOOR
actions:
  - action: button.press
    target:
      entity_id: button.front_door_relay_1
```

---

## Dashboard Example

```yaml
type: picture-glance
title: Front Door
camera_image: camera.front_door
entities:
  - button.front_door_relay_1
```

---

## Services

### `akuvox.update_tokens`
Manually update the API tokens without reconfiguring the integration.

```yaml
service: akuvox.update_tokens
data:
  entry_id: "your_config_entry_id"
  token: "new_token_value"
  refresh_token: "new_refresh_token_value"  # optional
```

### `akuvox.refresh_tokens`
Trigger an immediate token refresh using the stored refresh token.

```yaml
service: akuvox.refresh_tokens
data:
  entry_id: "your_config_entry_id"
```

---

## Troubleshooting

### Camera feeds not loading
- Ensure go2rtc is active (it is bundled with recent Home Assistant versions)
- Check that your HA server can reach the camera's IP on port 554 (UDP)
- Enable debug logging and look for `go2rtc registration` log lines

### Notifications without images
- Camera snapshots may take 1–3 seconds to become available
- The integration waits up to 5 seconds before firing the event
- Adjust this behaviour in the integration's **Configure** options

### Token expired errors
- Tokens auto-refresh every 6 days; check HA logs for refresh errors
- Use **Settings → Devices & Services → Akuvox SmartPlus → Configure** to update tokens manually
- Or call the `akuvox.update_tokens` service

### Enable Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.akuvox: debug
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Original integration by [@nimroddolev](https://github.com/nimroddolev/akuvox)
- Based on the [integration_blueprint](https://github.com/ludeeus/integration_blueprint) template

---

## Disclaimer

This integration is not affiliated with or endorsed by Akuvox. It is a community project provided as-is without warranty. Use at your own discretion.

---

[Community Forum](https://community.home-assistant.io/t/akuvox-smartplus-view-door-camera-feeds-open-doors-and-manage-temporary-keys/623187) · [GitHub Issues](https://github.com/wh1t35m1th/akuvox/issues)
