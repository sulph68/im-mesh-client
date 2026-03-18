"""
Shared constants and utilities for Meshtastic Web Client.
"""


# Default connection settings
DEFAULT_MESHTASTIC_PORT = 4403
DEFAULT_WEB_PORT = 8082

# Timing constants (seconds)
CONNECTION_SETTLE_DELAY = 3     # Wait after TCP connect for handshake
NODE_POPULATE_DELAY = 5         # Wait for node list to populate
RECONNECT_INTERVAL = 10         # Delay between reconnect attempts
CONNECTION_CHECK_INTERVAL = 5   # Health check interval when connected
SESSION_COOKIE_MAX_AGE = 86400  # 24 hours

# Image segment constraints
MIN_SEGMENT_LENGTH = 200
MAX_SEGMENT_LENGTH = 300
DEFAULT_SEGMENT_LENGTH = 200


# Meshtastic port number constants
# See: https://buf.build/meshtastic/protobufs/docs/main:meshtastic#meshtastic.PortNum
class PortNum:
    """Meshtastic application port numbers."""
    UNKNOWN_APP = 0
    TEXT_MESSAGE_APP = 1
    REMOTE_HARDWARE_APP = 2
    POSITION_APP = 3
    NODEINFO_APP = 4
    ROUTING_APP = 5
    ADMIN_APP = 6
    TEXT_MESSAGE_COMPRESSED_APP = 7
    WAYPOINT_APP = 8
    AUDIO_APP = 9
    TELEMETRY_APP = 67
    STORE_FORWARD_APP = 68
    RANGE_TEST_APP = 69
    TRACEROUTE_APP = 70
    NEIGHBORINFO_APP = 71
    PRIVATE_APP = 256
    ATAK_FORWARDER = 257


# String-to-int mapping for pypubsub portnum conversion
PORTNUM_MAP = {
    'TEXT_MESSAGE_APP': PortNum.TEXT_MESSAGE_APP,
    'REMOTE_HARDWARE_APP': PortNum.REMOTE_HARDWARE_APP,
    'POSITION_APP': PortNum.POSITION_APP,
    'NODEINFO_APP': PortNum.NODEINFO_APP,
    'ROUTING_APP': PortNum.ROUTING_APP,
    'ADMIN_APP': PortNum.ADMIN_APP,
    'TEXT_MESSAGE_COMPRESSED_APP': PortNum.TEXT_MESSAGE_COMPRESSED_APP,
    'WAYPOINT_APP': PortNum.WAYPOINT_APP,
    'AUDIO_APP': PortNum.AUDIO_APP,
    'TELEMETRY_APP': PortNum.TELEMETRY_APP,
    'STORE_FORWARD_APP': PortNum.STORE_FORWARD_APP,
    'RANGE_TEST_APP': PortNum.RANGE_TEST_APP,
    'TRACEROUTE_APP': PortNum.TRACEROUTE_APP,
    'NEIGHBORINFO_APP': PortNum.NEIGHBORINFO_APP,
    'PRIVATE_APP': PortNum.PRIVATE_APP,
    'ATAK_FORWARDER': PortNum.ATAK_FORWARDER,
    'UNKNOWN_APP': PortNum.UNKNOWN_APP,
}


# Broadcast address constant
BROADCAST_ADDR_HEX = 'FFFFFFFF'
BROADCAST_ADDR_INT = 4294967295  # 0xFFFFFFFF


def is_broadcast(to_node) -> bool:
    """Check if a destination address is a broadcast.
    
    Args:
        to_node: Destination node ID (str, int, or None)
        
    Returns:
        True if the destination is broadcast (None, ^ffffffff, or 4294967295)
    """
    if to_node is None:
        return True
    to_str = str(to_node).upper().lstrip('!')
    return to_str == BROADCAST_ADDR_HEX or to_str == str(BROADCAST_ADDR_INT)
