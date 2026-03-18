"""
Meshtastic client for TCP API communication.

Handles low-level connection, protobuf encoding/decoding, and packet management.
Uses real Meshtastic library when available, falls back to mock.
"""

import logging
from typing import Optional, Callable, Dict, Any, List
from .constants import DEFAULT_MESHTASTIC_PORT

# Try to import the real Meshtastic client
try:
    from .meshtastic_client_real import MeshtasticClientReal as MeshtasticClientImpl
    REAL_MESHTASTIC_AVAILABLE = True
except ImportError:
    REAL_MESHTASTIC_AVAILABLE = False

logger = logging.getLogger(__name__)

if not REAL_MESHTASTIC_AVAILABLE:
    logger.warning("Real Meshtastic library not available, using mock implementation")

class MeshtasticConnectionError(Exception):
    """Exception raised for Meshtastic connection issues."""
    pass

class MeshtasticClientMock:
    """
    Mock Meshtastic TCP API client for fallback when library is unavailable.
    """
    
    def __init__(self, host: str = "localhost", port: int = DEFAULT_MESHTASTIC_PORT,
                 connection_type: str = "tcp", serial_port: str = None):
        self.host = host
        self.port = port
        self.connection_type = connection_type
        self.serial_port = serial_port
        self.connected = False
        self.packet_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Mock databases
        self.nodes_db = {}
        self.channels_db = {
            0: {'index': 0, 'name': 'Primary', 'role': 'PRIMARY', 'psk': None},
            1: {'index': 1, 'name': 'LongFast', 'role': 'SECONDARY', 'psk': None}
        }

    # Stub so gateway.flush_pending_packets() doesn't error
    _pending_packets = []

    async def connect(self, timeout: int = 10) -> bool:
        """Mock connection."""
        import asyncio
        logger.info(f"Mock connection to Meshtastic at {self.host}:{self.port}")
        await asyncio.sleep(1)
        self.connected = True
        return True
    
    async def disconnect(self) -> None:
        """Mock disconnect."""
        self.connected = False
        logger.info("Mock disconnection completed")
    
    async def send_text_message(self, text: str, to_node: Optional[str] = None,
                               channel: int = 0, want_ack: bool = False):
        """Mock send text message."""
        if not self.connected:
            return False
        logger.info(f"Mock: sending '{text[:50]}' to {to_node or 'broadcast'}")
        return {'success': True, 'packet_id': None}

    async def send_binary_message(self, data: bytes, to_node: Optional[str] = None,
                                  channel: int = 0, portnum: int = 256,
                                  want_ack: bool = False):
        """Mock send binary message."""
        if not self.connected:
            return False
        return {'success': True, 'packet_id': None}
    
    def on_packet(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a packet callback."""
        self.packet_callbacks.append(callback)
    
    async def get_node_info(self) -> Dict[str, Any]:
        """Get mock node info."""
        return {
            'connected': self.connected, 'host': self.host, 'port': self.port,
            'node_id': 'mock_node', 'hw_model': 'MOCK_DEVICE', 'firmware_version': '1.0.0-mock'
        }
    
    def is_connected(self) -> bool:
        return self.connected
    
    async def get_channel_info(self) -> List[Dict[str, Any]]:
        return list(self.channels_db.values())

    async def get_device_settings(self) -> Dict[str, Any]:
        return {"device_type": "mock_meshtastic_node", "connection": {
            "host": self.host, "port": self.port, "connected": self.connected
        }}

    async def request_node_info_update(self) -> None:
        pass

    async def request_node_update(self) -> None:
        pass

    async def request_channel_update(self) -> None:
        pass

    def get_node_list(self) -> List[Dict[str, Any]]:
        return list(self.nodes_db.values())

    async def get_device_config(self) -> Dict[str, Any]:
        return await self.get_device_settings()

    async def flush_pending_packets(self) -> None:
        pass


# Use real implementation if available, otherwise fallback to mock
if REAL_MESHTASTIC_AVAILABLE:
    MeshtasticClient = MeshtasticClientImpl
else:
    MeshtasticClient = MeshtasticClientMock