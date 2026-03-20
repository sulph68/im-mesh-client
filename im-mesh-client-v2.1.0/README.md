# Im Mesh Client

A web-based Meshtastic mesh radio client for messaging, image transfer, and node management.
The key purpose of this was to investigate a way to compress images in 1/2/4 bit with an efficient encoding and compression model to transmit small images over the Meshtastic Network.

It makes use of RLE, Nibble and XOR methods to achieve reasonable compression of 1 bit images of size 64x64 together with heatshrink2.

It can transmit images using text strings with base64 encoding, or via the custom Meshtastic port as a binary message fully leveraginh the payload.

This client will assist in the transmission, encoding and reassembly of image segments.

This project was created using AI within [PAVE](https://github.com/cnrai/pave-dist).

## Requirements

- Python 3.9+
- Meshtastic node with TCP or Serial interface enabled
- Modern web browser (Chrome, Firefox, Safari, Edge)
- `openssl` (for automatic SSL certificate generation)

## Installation

1. Extract the release archive:

```bash
tar xzf im-mesh-client-v2.1.0.tar.gz
cd im-mesh-client-v2.1.0
```

2. Install Python dependencies:

```bash
pip3 install -r requirements.txt
```

3. Start the server:

```bash
./start_server.sh
```

The server will:
- Generate a self-signed SSL certificate if one does not exist
- Create a default `settings.json` if missing
- Start the HTTPS web server on port 8082
- Print connection URLs for local and network access

4. Open your browser to `https://localhost:8082` and accept the self-signed certificate warning.

5. On the login screen, enter your Meshtastic node's hostname/IP and port (default TCP port: 4403), or select Serial and enter the device path.

### Start Options

```bash
./start_server.sh                # Default: HTTPS on port 8082
./start_server.sh --no-ssl       # HTTP only (no certificate)
./start_server.sh --port 9443    # Custom port
./start_server.sh --cert /path/to/cert.pem --key /path/to/key.pem  # Custom certificate
```

### Configuration

Settings are stored in `settings.json` (auto-created on first run). You can also use environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_PORT` | 8082 | Server port |
| `SSL_ENABLED` | true | Enable HTTPS |
| `SSL_CERTFILE` | ./cert.pem | SSL certificate path |
| `SSL_KEYFILE` | ./key.pem | SSL private key path |

## Stopping the Server

Use any of the following:

```bash
# Option 1: Press CTRL-C in the terminal running the server

# Option 2: Use the stop script
./stop_server.sh

# Option 3: Kill the process directly
pkill -f "python3 main.py"
```

## Uninstall

1. Stop the server if it is running:

```bash
./stop_server.sh
```

2. Remove the installation directory:

```bash
cd ..
rm -rf im-mesh-client-v2.1.0
```

3. Optionally, remove the Python dependencies:

```bash
pip3 uninstall -y meshtastic fastapi uvicorn pyserial Pillow pypubsub aiosqlite heatshrink2 python-multipart jinja2 pydantic websockets
```

4. Browser data (message history, session mappings) is stored in your browser's localStorage. To clear it, open the browser developer tools (F12), go to Application > Local Storage, and delete entries prefixed with `meshtastic_`.

## License

Private - All rights reserved.

## Version

v2.1.0
