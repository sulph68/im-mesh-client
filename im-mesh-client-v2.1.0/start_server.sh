#!/bin/bash
#
# Im Mesh Client - Start Server
#
# This script:
#   1. Generates a self-signed SSL certificate if one doesn't exist
#   2. Creates a default settings.json if missing
#   3. Starts the web server with HTTPS
#
# Usage:
#   ./start_server.sh              # Use defaults (port 8082, certs in script dir)
#   ./start_server.sh --no-ssl     # Start without SSL (HTTP only)
#   ./start_server.sh --port 9443  # Override port
#
# Environment variables (override settings.json):
#   WEB_PORT=9443          - Server port
#   SSL_ENABLED=false      - Disable SSL
#   SSL_CERTFILE=/path     - Custom certificate path
#   SSL_KEYFILE=/path      - Custom key path
#

set -e

# Resolve script directory (cert default location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults
PORT="${WEB_PORT:-8082}"
SSL_ENABLED="${SSL_ENABLED:-true}"
CERT_FILE="${SSL_CERTFILE:-$SCRIPT_DIR/cert.pem}"
KEY_FILE="${SSL_KEYFILE:-$SCRIPT_DIR/key.pem}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-ssl)
            SSL_ENABLED="false"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --cert)
            CERT_FILE="$2"
            shift 2
            ;;
        --key)
            KEY_FILE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Im Mesh Client - Start Server"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --no-ssl        Start without SSL (HTTP only)"
            echo "  --port PORT     Server port (default: 8082)"
            echo "  --cert PATH     SSL certificate file path"
            echo "  --key PATH      SSL private key file path"
            echo "  --help          Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  WEB_PORT        Server port"
            echo "  SSL_ENABLED     Enable/disable SSL (true/false)"
            echo "  SSL_CERTFILE    SSL certificate path"
            echo "  SSL_KEYFILE     SSL private key path"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create default settings.json if it doesn't exist
if [ ! -f "$SCRIPT_DIR/settings.json" ]; then
    echo "Creating default settings.json..."
    cat > "$SCRIPT_DIR/settings.json" <<EOF
{
  "meshtastic": {
    "host": "localhost",
    "port": 4403,
    "auto_reconnect": true,
    "reconnect_delay": 10,
    "connection_timeout": 10
  },
  "encoding": {
    "mode": "rle_nibble_xor",
    "image_width": 64,
    "image_height": 64,
    "bit_depth": 1,
    "segment_length": 200,
    "enable_heatshrink": true
  },
  "web": {
    "host": "0.0.0.0",
    "port": $PORT,
    "debug": false,
    "ssl_enabled": $SSL_ENABLED,
    "ssl_certfile": "$CERT_FILE",
    "ssl_keyfile": "$KEY_FILE"
  },
  "storage": {
    "db_path": "meshtastic_client.db"
  }
}
EOF
    echo "settings.json created with default configuration"
fi

# Generate self-signed certificate if SSL enabled and certs missing
if [ "$SSL_ENABLED" = "true" ]; then
    if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        echo "Generating self-signed SSL certificate..."
        
        if ! command -v openssl &> /dev/null; then
            echo "ERROR: openssl is required for SSL. Install it or use --no-ssl"
            exit 1
        fi
        
        openssl req -x509 -newkey rsa:2048 \
            -keyout "$KEY_FILE" \
            -out "$CERT_FILE" \
            -days 365 \
            -nodes \
            -subj "/CN=im-mesh-client/O=ImMesh/C=SG" \
            2>/dev/null
        
        echo "SSL certificate generated:"
        echo "  Certificate: $CERT_FILE"
        echo "  Private key: $KEY_FILE"
        echo "  Valid for:   365 days"
        echo ""
        echo "NOTE: This is a self-signed certificate. Browsers will show a security warning."
        echo "      Accept the warning to proceed, or replace with a proper certificate."
    else
        echo "SSL certificate found: $CERT_FILE"
    fi
    
    PROTOCOL="https"
else
    PROTOCOL="http"
fi

# Export environment for Python
export WEB_PORT="$PORT"
export SSL_ENABLED="$SSL_ENABLED"
export SSL_CERTFILE="$CERT_FILE"
export SSL_KEYFILE="$KEY_FILE"

# Get local IP addresses for connection instructions
LOCAL_IPS=""
if command -v hostname &> /dev/null; then
    LOCAL_IPS=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^$' | head -3)
fi
if [ -z "$LOCAL_IPS" ] && command -v ip &> /dev/null; then
    LOCAL_IPS=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -3)
fi

echo ""
echo "=========================================="
echo "  Im Mesh Client"
echo "=========================================="
echo "  Port:     $PORT"
echo "  SSL:      $SSL_ENABLED"
if [ "$SSL_ENABLED" = "true" ]; then
echo "  Cert:     $CERT_FILE"
echo "  Key:      $KEY_FILE"
fi
echo "  Config:   $SCRIPT_DIR/settings.json"
echo ""
echo "  Connect from this machine:"
echo "    $PROTOCOL://localhost:$PORT"
echo ""
if [ -n "$LOCAL_IPS" ]; then
echo "  Connect from other devices on your network:"
while IFS= read -r ip; do
    [ -n "$ip" ] && echo "    $PROTOCOL://$ip:$PORT"
done <<< "$LOCAL_IPS"
echo ""
fi
if [ "$SSL_ENABLED" = "true" ]; then
echo "  NOTE: Using a self-signed certificate."
echo "  Your browser will show a security warning."
echo "  Accept it to proceed, or replace cert.pem/key.pem"
echo "  with certificates from a trusted CA."
echo ""
fi
echo "  Supports TCP and Serial connections to"
echo "  Meshtastic nodes from the web interface."
echo "=========================================="
echo ""

# Start the server
exec python3 "$SCRIPT_DIR/main.py"
