# im-mesh-client v2.4.0

A web-based client for Meshtastic mesh radio networks. Connects to your Meshtastic node
over TCP (WiFi) or Serial (USB) and provides a browser interface for messaging, image
transfer, node management, scheduled messages, auto-response, and Telegram forwarding.



---

## Table of Contents

1. [Requirements](#requirements)
2. [Install](#install)
3. [Start / Stop](#start--stop)
4. [Connect to Meshtastic](#connect-to-meshtastic)
5. [Configuration (settings.json)](#configuration-settingsjson)
6. [Backup and Restore](#backup-and-restore)
7. [Scheduler](#scheduler)
8. [Auto Responder](#auto-responder)
9. [Telegram Forwarder](#telegram-forwarder)
10. [Node Export API](#node-export-api)
11. [Sample Scripts](#sample-scripts)
12. [Uninstall](#uninstall)

---

## Requirements

- **Python 3.9+**
- **Meshtastic node** with TCP interface enabled (default port 4403), or Serial/USB connection
- **Modern web browser** (Chrome, Firefox, Safari, Edge)

---

## Install

```bash
# 1. Extract the tarball
tar -xzf im-mesh-client-v2.4.0.tar.gz
cd im-mesh-client-v2.4.0

# 2. Install Python dependencies
pip3 install -r requirements.txt

# 3. Copy the sample config and edit it
cp settings.json.sample settings.json
# Edit settings.json — at minimum set meshtastic.host to your node's IP
```

The server auto-generates a self-signed TLS certificate (`cert.pem` / `key.pem`) on first
start if SSL is enabled (the default).

---

## Start / Stop

```bash
# Start with HTTPS on default port 8082 (recommended)
./start_server.sh

# Start without SSL
./start_server.sh --no-ssl

# Start on a custom port
./start_server.sh --port 9443

# Stop the server
./stop_server.sh
```

Open your browser to **`https://localhost:8082`** (or the IP of the machine running the
server). Accept the self-signed certificate warning on first visit.

---

## Connect to Meshtastic

On the login screen, choose a connection type:

| Type | Input | Example |
|---|---|---|
| **TCP** | Host and port of the Meshtastic TCP bridge | `192.168.1.100` port `4403` |
| **Serial** | Device path | `/dev/ttyUSB0`, `/dev/ttyACM0`, `COM3` |

The default TCP bridge port is **4403**. Enable the TCP interface in the Meshtastic app
under **Radio config → Network → WiFi → TCP server**.

---

## Configuration (settings.json)

Copy `settings.json.sample` to `settings.json`. The server loads it at startup — restart
after any changes.

```json
{
  "meshtastic": {
    "host": "localhost",
    "port": 4403,
    "auto_reconnect": true,
    "reconnect_delay": 10,
    "connection_timeout": 10,
    "message_delay": 5,
    "character_limit": 220
  },
  "encoding": {
    "mode": "rle_nibble_xor",
    "image_width": 64,
    "image_height": 64,
    "bit_depth": 1,
    "segment_length": 200,
    "enable_heatshrink": true,
    "segment_delay": 15
  },
  "web": {
    "host": "0.0.0.0",
    "port": 8082,
    "debug": false,
    "ssl_enabled": true,
    "ssl_certfile": "./cert.pem",
    "ssl_keyfile": "./key.pem",
    "export_enabled": true
  },
  "storage": {
    "db_path": "meshtastic_client.db"
  },
  "sched_message": {
    "enabled": false,
    "working_directory": "./sched_messages",
    "commands": "./sched_messages/commands",
    "max_lines": 5,
    "host": "127.0.0.1",
    "message_history": 24
  },
  "auto_responder": {
    "enabled": false,
    "host": "127.0.0.1",
    "working_directory": "./auto_responder",
    "history_context": 20,
    "max_lines": 5,
    "responder_prefix": "",
    "eliza_1966_prefix": "Eliza (1966)"
  },
  "telegram": {
    "enabled": false,
    "bot_token": "",
    "host": "127.0.0.1",
    "directory": "./telegram_forwarder"
  }
}
```

### Settings Reference

#### `meshtastic`

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | string | `"localhost"` | IP or hostname of the Meshtastic TCP bridge |
| `port` | int | `4403` | TCP bridge port |
| `auto_reconnect` | bool | `true` | Reconnect automatically on connection loss |
| `reconnect_delay` | int | `10` | Seconds between reconnect attempts |
| `connection_timeout` | int | `10` | TCP connect timeout in seconds |
| `message_delay` | int | `5` | Minimum seconds between outgoing radio sends (send pacing) |
| `character_limit` | int | `220` | Characters before auto-split kicks in |

#### `encoding`

| Key | Type | Default | Description |
|---|---|---|---|
| `mode` | string | `"rle_nibble_xor"` | Image encoding algorithm |
| `image_width` | int | `64` | Default image width in pixels |
| `image_height` | int | `64` | Default image height in pixels |
| `bit_depth` | int | `1` | Bits per pixel (`1` = monochrome) |
| `segment_length` | int | `200` | Max bytes per mesh segment |
| `enable_heatshrink` | bool | `true` | Apply heatshrink compression to encoded data |
| `segment_delay` | int | `15` | Seconds between sending each image segment |

#### `web`

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | string | `"0.0.0.0"` | Bind interface (`"0.0.0.0"` = all interfaces) |
| `port` | int | `8082` | Web server port |
| `debug` | bool | `false` | FastAPI debug mode — disable in production |
| `ssl_enabled` | bool | `true` | Enable HTTPS |
| `ssl_certfile` | string | `"./cert.pem"` | TLS certificate path |
| `ssl_keyfile` | string | `"./key.pem"` | TLS private key path |
| `export_enabled` | bool | `true` | Enable the `GET /api/nodes/export` endpoint |

#### `storage`

| Key | Type | Default | Description |
|---|---|---|---|
| `db_path` | string | `"meshtastic_client.db"` | SQLite database path (session data) |

#### `sched_message`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the Scheduler feature |
| `working_directory` | string | `"./sched_messages"` | Root directory for schedule files (empty → `./sched_messages/`) |
| `commands` | string | `"./sched_messages/commands"` | Directory for command scripts |
| `max_lines` | int | `5` | Max output lines per command message |
| `host` | string | `"127.0.0.1"` | Meshtastic host this scheduler is scoped to |
| `message_history` | int | `24` | Hours of history used by `{{LAST_MSG}}` substitution |

#### `auto_responder`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable the Auto Responder feature |
| `host` | string | `"127.0.0.1"` | Meshtastic host this AR is scoped to |
| `working_directory` | string | `"./auto_responder"` | Root directory for conversation rule folders |
| `history_context` | int | `20` | Lines of conversation history passed to scripts |
| `max_lines` | int | `5` | Max script output lines per response message |
| `responder_prefix` | string | `""` | Optional text prepended to every auto-response |
| `eliza_1966_prefix` | string | `"Eliza (1966)"` | Display name used for Eliza mode replies |

#### `telegram`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable Telegram Forwarder |
| `bot_token` | string | `""` | Bot API token from [@BotFather](https://t.me/BotFather) |
| `host` | string | `"127.0.0.1"` | Meshtastic host this TF is scoped to |
| `directory` | string | `"./telegram_forwarder"` | Working directory for TF configs |

---

## Backup and Restore

```bash
# Create a backup archive (timestamped .tar.gz)
./backup_settings.sh                        # saves to current directory
./backup_settings.sh /path/to/dest/         # saves to a specified directory

# Restore from backup
./restore_settings.sh backup_20260418_120000.tar.gz        # prompts before overwriting
./restore_settings.sh backup_20260418_120000.tar.gz -y     # overwrite without prompting
```

The backup includes: `settings.json`, `cert.pem`/`key.pem`, `auto_responder/`,
`sched_messages/`, and `telegram_forwarder/configs/`.

After restoring, restart the server:
```bash
./stop_server.sh && ./start_server.sh
```

---

## Scheduler

Sends messages or runs commands on a cron schedule. Configure via the **🕐 Scheduler**
modal in the web UI, or directly via the `/api/scheduler/*` REST API.

**Variable substitution** — available in message text:

| Variable | Replaced with |
|---|---|
| `{{DATE}}` | Current date (YYYY-MM-DD) |
| `{{TIME}}` | Current time (HH:MM) |
| `{{LAST_MSG}}` | Last received message in the conversation |

Set `sched_message.enabled: true` in `settings.json` to activate.

---

## Auto Responder

Automatically replies to incoming messages. Configure via the **🤖 Auto Respond** modal.

**Reply modes:**

| Mode | Behaviour |
|---|---|
| `eliza` | Built-in Eliza (1966) chatbot (default) |
| `fixed` | Always reply with a configured static text |
| `script` | Run an executable script; its stdout is sent as the reply |

**AI script setup:**

1. Copy `responder.sample` to your conversation folder and make it executable:
   ```bash
   cp responder.sample auto_responder/ch0_longfast/responder
   chmod +x auto_responder/ch0_longfast/responder
   ```
2. Set your [OpenRouter API key](https://openrouter.ai/keys) — either in the script or via the environment variable `OPENROUTER_API_KEY`.
3. In the AR modal, set the rule's mode to **"Use responder script"** and save.

The `{{MESSAGE}}` variable is available in fixed-reply text and script environments.

Set `auto_responder.enabled: true` in `settings.json` to activate.

---

## Telegram Forwarder

Forwards mesh messages (text and images) to Telegram chats.

### Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and copy the token.
2. Add the bot to your Telegram group or channel and grant it message permissions.
3. Get the `chat_id`: send a message to the group and check  
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Set in `settings.json`:
   ```json
   "telegram": {
     "enabled": true,
     "bot_token": "123456:ABC-your-token-here",
     "host": "127.0.0.1",
     "directory": "./telegram_forwarder"
   }
   ```
5. Restart the server.
6. Click the **✈ Telegram** button in the web UI to add per-conversation forwarding rules.

---

## Node Export API

Export the full node list as JSON — useful for integration with external tools.

```bash
# Requires export_enabled: true in settings.json
./export_sample.sh <device-ip>

# Or direct curl (no session cookie needed)
curl -sk "https://localhost:8082/api/nodes/export?host=192.168.1.1&port=4403"

# Filter fields
curl -sk ".../api/nodes/export?host=...&include=id,name,snr,lastSeen"
curl -sk ".../api/nodes/export?host=...&exclude=position,battery"
```

---

## Sample Scripts

| Script | Purpose |
|---|---|
| `responder.sample` | OpenRouter AI responder template for the Auto Responder |
| `export_sample.sh` | Example node export curl calls with field filtering |

---

## Uninstall

```bash
# 1. Stop the server
./stop_server.sh

# 2. Optionally back up your data first
./backup_settings.sh

# 3. Delete the installation directory
cd ..
rm -rf im-mesh-client-v2.4.0/
```

Runtime data files created outside the install directory: none — everything is stored
inside the installation folder.
