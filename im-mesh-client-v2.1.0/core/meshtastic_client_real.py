"""
Real Meshtastic client using the official Meshtastic Python library.

Handles actual Meshtastic TCP API communication with proper protobuf support.

Composed from two mixins:
- PacketProcessorMixin: packet receive, processing, dedup, dispatch
- NodeDataMixin: node/channel data extraction, queries, helpers
"""

import asyncio
import logging
from collections import deque
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

from .constants import (
    PortNum, PORTNUM_MAP,
    CONNECTION_SETTLE_DELAY, NODE_POPULATE_DELAY,
    DEFAULT_MESHTASTIC_PORT,
)
from .packet_processor import PacketProcessorMixin
from .node_data import NodeDataMixin

# Import official Meshtastic library
try:
    import meshtastic
    import meshtastic.tcp_interface
    MESHTASTIC_AVAILABLE = True
except ImportError:
    MESHTASTIC_AVAILABLE = False
    logging.warning("Official Meshtastic library not available, falling back to mock implementation")

try:
    import meshtastic.serial_interface
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

logger = logging.getLogger(__name__)

class MeshtasticConnectionError(Exception):
    """Exception raised for Meshtastic connection issues."""
    pass

class MeshtasticClientReal(PacketProcessorMixin, NodeDataMixin):
    """
    Real Meshtastic TCP client using official library.
    
    Provides actual communication with Meshtastic devices via TCP interface.
    
    Composed from:
    - PacketProcessorMixin: _on_receive, _build_packet_dict, _process_decoded_payload,
      _handle_text_message, _handle_binary_message, _handle_routing_message,
      _is_self_echo, _dispatch_packet, _portnum_to_int, _pubsub_*_handler
    - NodeDataMixin: _safe_get, _extract_user_info, _extract_sub_dict,
      _extract_scalar_attrs, _encode_psk, _process_channel, _build_node_data,
      get_node_info, get_node_list, get_channel_info, get_device_settings,
      request_node_info_update, request_channel_update, request_node_update,
      get_device_config, is_connected
    """
    
    def __init__(self, host: str = "localhost", port: int = DEFAULT_MESHTASTIC_PORT,
                 connection_type: str = "tcp", serial_port: Optional[str] = None):
        self.host = host
        self.port = port
        self.connection_type = connection_type  # "tcp" or "serial"
        self.serial_port = serial_port  # e.g., "/dev/ttyUSB0"
        self.interface = None
        self.connected = False
        self.packet_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.nodes_db = {}
        self.channels_db = {}
        self.my_node_info = None
        self._event_loop = None  # Reference to the main asyncio event loop
        self._pending_packets = []  # Queue for packets that arrive before event loop is ready
        # Track processed packet IDs to avoid duplicate processing from pypubsub topic hierarchy
        self._processed_packet_ids = deque(maxlen=500)  # Ordered deque with auto-eviction
        self._processed_packet_id_set = set()  # O(1) membership check
        # CRITICAL: pypubsub uses WEAK references to listeners.
        # If listeners are closures/lambdas defined in a function, they get garbage collected.
        # We store strong references as instance attributes so they survive GC.
        self._pubsub_on_receive = None
        self._pubsub_on_connection = None
        self._pubsub_on_connection_lost = None
    
    # ----- PubSub management -----
    
    def _setup_pubsub(self) -> None:
        """Register pypubsub callbacks with strong references.
        
        CRITICAL: pypubsub holds WEAK references to listeners. Closures/lambdas
        get garbage collected, causing callbacks to silently stop. We store bound
        methods as instance attributes to keep strong references.
        """
        from pubsub import pub
        
        self._cleanup_pubsub()
        
        # Store bound methods as instance attributes (strong references)
        self._pubsub_on_receive = self._pubsub_receive_handler
        self._pubsub_on_connection = self._pubsub_connection_handler
        self._pubsub_on_connection_lost = self._pubsub_connection_lost_handler
        
        pub.subscribe(self._pubsub_on_receive, "meshtastic.receive")
        pub.subscribe(self._pubsub_on_connection, "meshtastic.connection.established")
        pub.subscribe(self._pubsub_on_connection_lost, "meshtastic.connection.lost")
        
        logger.info("Registered pypubsub callbacks (strong refs)")

    def _cleanup_pubsub(self) -> None:
        """Unsubscribe any existing pypubsub callbacks."""
        from pubsub import pub
        
        for attr, topic in [
            ('_pubsub_on_receive', 'meshtastic.receive'),
            ('_pubsub_on_connection', 'meshtastic.connection.established'),
            ('_pubsub_on_connection_lost', 'meshtastic.connection.lost'),
        ]:
            handler = getattr(self, attr, None)
            if handler is not None:
                try:
                    pub.unsubscribe(handler, topic)
                except (ValueError, RuntimeError):
                    pass  # Not subscribed or already cleaned up

    # ----- Connection lifecycle -----

    async def _wait_for_nodes(self) -> None:
        """Wait for interface nodes to populate after connection."""
        has_nodes = hasattr(self.interface, 'nodes')
        nodes_count = len(self.interface.nodes) if has_nodes and self.interface.nodes else 0
        if nodes_count == 0:
            await asyncio.sleep(NODE_POPULATE_DELAY)

    async def connect(self, timeout: int = 10) -> bool:
        """
        Connect to Meshtastic device via TCP or Serial.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connection successful, False otherwise
        """
        if not MESHTASTIC_AVAILABLE:
            logger.error("Meshtastic library not available")
            return False
        
        try:
            self._event_loop = asyncio.get_running_loop()
            
            if self.connection_type == "serial":
                # Serial connection
                if not SERIAL_AVAILABLE:
                    logger.error("Meshtastic serial interface not available")
                    return False
                
                device = self.serial_port or self.host
                # Strip serial:// prefix if present
                if device.startswith("serial://"):
                    device = device[len("serial://"):]
                
                logger.info(f"Connecting to Meshtastic via serial: {device}")
                self.interface = meshtastic.serial_interface.SerialInterface(
                    devPath=device,
                    connectNow=True,
                    noProto=False
                )
            else:
                # TCP connection (default)
                logger.info(f"Connecting to Meshtastic at {self.host}:{self.port}")
                self.interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=self.host,
                    portNumber=self.port,
                    connectNow=True,
                    noProto=False
                )
            
            self._setup_pubsub()
            
            # Wait for connection to establish
            await asyncio.sleep(CONNECTION_SETTLE_DELAY)
            
            is_connected = hasattr(self.interface, 'isConnected') and self.interface.isConnected
            if is_connected:
                self.connected = True
                await self._wait_for_nodes()
                logger.info("Connected to Meshtastic device successfully")
                await self._request_initial_data()
                return True
            else:
                logger.warning("Failed to establish connection - interface not connected")
                return False
                
        except (ConnectionError, OSError, TimeoutError, RuntimeError) as e:
            logger.warning(f"Failed to connect to Meshtastic: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Meshtastic device."""
        try:
            self.connected = False
            
            # Unsubscribe pypubsub callbacks to avoid stale references
            self._cleanup_pubsub()
            
            if self.interface:
                self.interface.close()
                self.interface = None
            
            logger.info("Disconnected from Meshtastic device")
            
        except (ConnectionError, OSError, RuntimeError) as e:
            logger.warning(f"Error during disconnect: {e}")
    
    # ----- Connection event handlers -----
    
    def _on_connection(self, interface, topic=None):
        """Handle connection established events."""
        try:
            logger.debug(f"Connection established event: {topic}")
            self.connected = True
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Error in connection callback: {e}")
    
    def _on_connection_lost(self, interface):
        """Handle connection lost events."""
        try:
            logger.warning("Connection lost event received from Meshtastic library")
            self.connected = False
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Error in connection lost callback: {e}")
    
    # ----- Database management -----
    
    def _update_databases(self, packet_dict: Dict[str, Any]) -> None:
        """Update internal node and channel databases."""
        try:
            # Update nodes database from interface
            if self.interface and hasattr(self.interface, 'nodes'):
                logger.debug(f"Processing {len(self.interface.nodes)} nodes from interface")
                for node_id, node_data in self.interface.nodes.items():
                    try:
                        user_info = self._extract_user_info(node_data)
                        short_name = user_info['shortName'] or f'Node_{node_id}'
                        long_name = user_info['longName'] or f'Unknown_{node_id}'
                        hw_model = user_info['hwModel']
                        
                        self.nodes_db[node_id] = {
                            'node_id': node_id,
                            'short_name': short_name,
                            'long_name': long_name,
                            'hw_model': hw_model,
                            'is_online': True,
                            'last_heard': datetime.now().isoformat(),
                            'snr': packet_dict.get('rx_snr'),
                            'rssi': packet_dict.get('rx_rssi')
                        }
                        
                        logger.debug(f"Added/updated node {node_id}: {short_name}")
                        
                    except (KeyError, AttributeError, TypeError, ValueError) as node_error:
                        logger.warning(f"Error processing node {node_id}: {node_error}")
                        logger.debug(f"Node data structure: {type(node_data)} - {node_data}")
            
            # Update our node info
            if self.interface and hasattr(self.interface, 'myInfo'):
                self.my_node_info = self.interface.myInfo
                
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Error updating databases: {e}")
            if self.interface and hasattr(self.interface, 'nodes'):
                logger.debug(f"Sample node data: {list(self.interface.nodes.items())[:1]}")
    
    # ----- Callback management -----
    
    async def _notify_callbacks(self, packet_dict: Dict[str, Any]) -> None:
        """Notify all packet callbacks."""
        msg_type = packet_dict.get('message_type', 'unknown')
        if not self.packet_callbacks:
            if msg_type in ('text', 'binary', 'routing'):
                logger.warning(f"No packet callbacks registered for {msg_type} message from {packet_dict.get('from_node', '?')}")
            return
        for callback in self.packet_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(packet_dict)
                else:
                    callback(packet_dict)
            except Exception as e:  # Broad: unknown user callback signatures
                logger.warning(f"Error in packet callback: {e}", exc_info=True)
    
    async def flush_pending_packets(self) -> None:
        """Flush any packets that were queued before the event loop was available."""
        if not self._pending_packets:
            return
        count = len(self._pending_packets)
        logger.info(f"Flushing {count} pending packets queued during startup")
        packets = self._pending_packets[:]
        self._pending_packets.clear()
        for pkt in packets:
            try:
                await self._notify_callbacks(pkt)
            except Exception as e:  # Broad: unknown callback chain
                logger.warning(f"Error flushing pending packet: {e}")
    
    # ----- Initial data loading -----
    
    async def _request_initial_data(self) -> None:
        """Request initial node and channel data after connection."""
        try:
            if not self.interface:
                return
            
            logger.info("Requesting initial node and channel data")
            await asyncio.sleep(1)
            
            # Populate nodes database from interface
            if hasattr(self.interface, 'nodes') and self.interface.nodes:
                self._update_databases({})
            
            # Get own node info
            if hasattr(self.interface, 'getMyNodeInfo'):
                self.my_node_info = self.interface.getMyNodeInfo()
            
            # Cache channel data
            if hasattr(self.interface, 'localNode') and hasattr(self.interface.localNode, 'channels'):
                for i, channel in enumerate(self.interface.localNode.channels):
                    if channel and channel.settings:
                        channel_name = getattr(channel.settings, 'name', f'Channel {i}') or f'Channel {i}'
                        psk = getattr(channel.settings, 'psk', None)
                        psk_str = None
                        if psk:
                            try:
                                psk_str = psk.hex() if isinstance(psk, bytes) else str(psk)
                            except (AttributeError, TypeError):
                                pass
                        self.channels_db[i] = {
                            'index': i, 'name': channel_name,
                            'role': 'PRIMARY' if i == 0 else 'SECONDARY',
                            'psk': psk_str, 'module_settings': {}
                        }
            
            logger.debug(f"Initial data: {len(self.nodes_db)} nodes, {len(self.channels_db)} channels")
            
        except (AttributeError, KeyError, TypeError, ConnectionError) as e:
            logger.warning(f"Error requesting initial data: {e}")
    
    # ----- Send methods -----
    
    async def send_text_message(self, text: str, to_node: Optional[str] = None,
                               channel: int = 0, want_ack: bool = False):
        """
        Send a text message.
        
        Args:
            text: Message text to send
            to_node: Target node ID (None for broadcast)
            channel: Channel to send on
            want_ack: Request acknowledgment
            
        Returns:
            The sent packet (dict with 'id' for ack tracking), or False on failure
        """
        try:
            if not self.interface or not self.connected:
                logger.warning("Cannot send message: not connected")
                return False
                
            # Send message using interface - returns sent packet with id field
            if to_node:
                # Direct message to specific node
                sent_packet = self.interface.sendText(
                    text=text,
                    destinationId=to_node,
                    wantAck=want_ack,
                    channelIndex=channel
                )
            else:
                # Broadcast message
                sent_packet = self.interface.sendText(
                    text=text,
                    wantAck=want_ack,
                    channelIndex=channel
                )
            
            # Extract packet ID for ack tracking
            packet_id = None
            if sent_packet:
                if isinstance(sent_packet, dict):
                    packet_id = sent_packet.get('id')
                else:
                    packet_id = getattr(sent_packet, 'id', None)
            
            logger.info(f"Sent text message: {text[:50]}... to {'node ' + to_node if to_node else 'broadcast'} (packetId={packet_id})")
            return {'success': True, 'packet_id': packet_id}
            
        except (ConnectionError, OSError, RuntimeError, TypeError) as e:
            logger.warning(f"Failed to send text message: {e}")
            return False
    
    async def send_binary_message(self, data: bytes, to_node: Optional[str] = None,
                                  channel: int = 0, portnum: int = PortNum.PRIVATE_APP,
                                  want_ack: bool = False) -> bool:
        """
        Send a binary message using PRIVATE_APP (portnum 256) or custom portnum.
        
        This enables custom app-to-app binary communication over the mesh.
        
        Args:
            data: Binary data to send
            to_node: Target node ID (None for broadcast)
            channel: Channel to send on
            portnum: Port number (default 256 = PRIVATE_APP / BINARY_MESSAGE_APP)
            want_ack: Request acknowledgment
            
        Returns:
            True if message was sent successfully
        """
        try:
            if not self.interface or not self.connected:
                logger.warning("Cannot send binary message: not connected")
                return False
            
            if to_node:
                sent_packet = self.interface.sendData(
                    data,
                    destinationId=to_node,
                    portNum=portnum,
                    wantAck=want_ack,
                    channelIndex=channel
                )
            else:
                sent_packet = self.interface.sendData(
                    data,
                    portNum=portnum,
                    wantAck=want_ack,
                    channelIndex=channel
                )
            
            # Extract packet ID for ack tracking
            packet_id = None
            if sent_packet:
                if isinstance(sent_packet, dict):
                    packet_id = sent_packet.get('id')
                else:
                    packet_id = getattr(sent_packet, 'id', None)
            
            logger.info(f"Sent binary message ({len(data)} bytes, portnum={portnum}) to {'node ' + to_node if to_node else 'broadcast'} (packetId={packet_id})")
            return {'success': True, 'packet_id': packet_id}
            
        except (ConnectionError, OSError, RuntimeError, TypeError) as e:
            logger.warning(f"Failed to send binary message: {e}")
            return False
    
    def on_packet(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a packet callback."""
        self.packet_callbacks.append(callback)
