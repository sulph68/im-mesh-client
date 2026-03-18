# Im Mesh Client

A web-based Meshtastic mesh radio client for messaging and node management.

## Features

- **Multi-tenant**: Multiple browser sessions can connect to different Meshtastic nodes simultaneously
- **TCP & Serial**: Connect to Meshtastic nodes via TCP/IP or local serial device
- **Text Messaging**: Send and receive text messages on channels or direct to nodes
- **Binary Messaging**: Custom binary app-to-app communication over the mesh (PRIVATE_APP)
- **Image Encoding**: Encode images for transmission over Meshtastic with multiple sizes and encoding modes
- **Image Reassembly**: Automatically reassemble received image segments back into images
- **Node Management**: View all mesh nodes with details, positions, battery, signal info
- **Channel Config**: Read channel configuration from connected nodes
- **Node Map**: Interactive Leaflet map showing node positions with clustering
- **Real-time Updates**: WebSocket-based live message delivery with heartbeat monitoring
- **ACK Tracking**: Visual acknowledgment status for sent messages
- **HTTPS by Default**: Self-signed certificate auto-generation
- **PWA Support**: Installable as a Progressive Web App with offline caching
- **Mobile Optimized**: Responsive design with touch-friendly mobile layout

## Quick Start

```bash
# Install dependencies
pip3 install -r requirements.txt

# Start the server (HTTPS, auto-generates certificate)
./start_server.sh

# Or start without SSL
./start_server.sh --no-ssl

# Or start with custom port
./start_server.sh --port 9443
```

Then open your browser to `https://localhost:8082` (accept the self-signed certificate warning).

## Connection Types

### TCP Connection
Enter the hostname/IP and port of your Meshtastic node's TCP interface (default port: 4403).

### Serial Connection
Select "Serial" on the login screen and enter the device path:
- Linux: `/dev/ttyUSB0`, `/dev/ttyACM0`
- macOS: `/dev/cu.usbmodem*`
- Windows: `COM3`, `COM4`

## Requirements

- Python 3.9+
- Meshtastic node with TCP or Serial interface enabled
- Modern web browser (Chrome, Firefox, Safari, Edge)

## Dependencies

- `meshtastic` - Official Meshtastic Python library
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pyserial` - Serial port access
- `Pillow` - Image processing
- `pypubsub` - Internal event system
- `aiosqlite` - Async SQLite for session databases

## Image Encoding

Supported image sizes for mesh transmission:
| Size | Segments | Orientation |
|------|----------|-------------|
| 128x64 | 4 | Landscape |
| 96x48 | 3 | Landscape |
| 64x32 | 2 | Landscape small |
| 64x64 | 3 | Square medium |
| 48x48 | 2 | Square small |
| 32x32 | 2 | Square tiny |

## Configuration

Settings can be configured via:
1. `settings.json` (auto-created on first run)
2. Environment variables (`WEB_PORT`, `SSL_ENABLED`, etc.)
3. Command-line flags (`--port`, `--no-ssl`, `--cert`, `--key`)

## Project Structure

```
im-mesh-client/
├── main.py                    # Application entry point
├── start_server.sh            # Startup script with SSL/cert management
├── requirements.txt           # Python dependencies
├── core/                      # Core business logic
│   ├── gateway.py             # Connection & message flow coordinator
│   ├── meshtastic_client.py   # Client factory (real/mock)
│   ├── meshtastic_client_real.py  # Real Meshtastic TCP/Serial client
│   ├── packet_processor.py    # Packet receive & normalization
│   ├── node_data.py           # Node/channel data extraction
│   ├── packet_handler.py      # Packet type dispatcher
│   ├── fragment_reassembler.py # Binary segment reassembly
│   ├── message_router.py      # WebSocket message routing
│   ├── session_manager.py     # Multi-tenant session management
│   └── constants.py           # Shared constants
├── api/                       # REST & WebSocket API
│   ├── rest_api_multitenant.py # FastAPI app setup
│   ├── websocket_api_multitenant.py # WebSocket handler
│   ├── models.py              # Pydantic request/response models
│   └── routes/                # Route handlers
├── storage/                   # Database layer
│   ├── database.py            # SQLite wrapper
│   └── node_store.py          # Node data persistence
├── encoding/                  # Image codec adapters
│   ├── encoder_adapter.py     # Image encoder
│   └── decoder_adapter.py     # Image decoder
├── config/
│   └── settings.py            # Configuration & SSL management
└── web/static/                # Frontend
    ├── index.html             # Single-page application
    ├── css/                   # Stylesheets (5 files)
    ├── js/                    # JavaScript modules (9 files)
    ├── sw.js                  # Service worker
    └── manifest.json          # PWA manifest
```

## License

Private - All rights reserved.

## Version

v2.1.0
