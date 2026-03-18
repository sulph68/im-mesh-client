"""
Gateway core for managing Meshtastic connection and message flow.

Central coordinator for all Meshtastic communication and internal routing.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from .meshtastic_client import MeshtasticClient
from .packet_handler import PacketHandler
from .fragment_reassembler import FragmentReassembler
from .message_router import MessageRouter
from .constants import PortNum, CONNECTION_CHECK_INTERVAL
from storage.database import Database
from storage.node_store import NodeStore
from config.settings import Settings

logger = logging.getLogger(__name__)

class Gateway:
    """
    Central gateway for Meshtastic communication.
    
    Manages the connection to Meshtastic devices, coordinates packet processing,
    and handles message routing throughout the application.
    """
    
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        
        # Determine connection type
        connection_type = getattr(settings.meshtastic, 'connection_type', 'tcp')
        serial_port = getattr(settings.meshtastic, 'serial_port', None)
        
        # Core components
        self.meshtastic_client = MeshtasticClient(
            host=settings.meshtastic.host,
            port=settings.meshtastic.port,
            connection_type=connection_type,
            serial_port=serial_port
        )
        
        self.message_router = MessageRouter()
        self.node_store = NodeStore(database)
        self.fragment_reassembler = FragmentReassembler(database, self.message_router)
        self.packet_handler = PacketHandler(
            self.node_store,
            self.message_router, self.fragment_reassembler
        )
        
        # State
        self.running = False
        self.connection_task: Optional[asyncio.Task] = None
        self.reconnect_delay = settings.meshtastic.reconnect_delay
        self.auto_reconnect = settings.meshtastic.auto_reconnect
        self._connection_ready = asyncio.Event()  # Signals when first connection attempt is done
        
    async def start(self) -> None:
        """Start the gateway and all its components."""
        try:
            logger.info("Starting Meshtastic gateway")
            
            # Start fragment reassembler
            await self.fragment_reassembler.start()
            
            # Register packet callback
            self.meshtastic_client.on_packet(self.packet_handler.handle_packet)
            
            # Start connection management
            self.running = True
            self.connection_task = asyncio.create_task(self._manage_connection())
            
            logger.info("Meshtastic gateway started")
            
        except (ConnectionError, OSError, RuntimeError) as e:
            logger.error(f"Failed to start gateway: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the gateway and cleanup resources."""
        try:
            logger.info("Stopping Meshtastic gateway")
            
            self.running = False
            
            # Cancel connection task
            if self.connection_task:
                self.connection_task.cancel()
                try:
                    await self.connection_task
                except asyncio.CancelledError:
                    pass
                self.connection_task = None
            
            # Disconnect from Meshtastic
            if self.meshtastic_client.is_connected():
                await self.meshtastic_client.disconnect()
            
            # Stop fragment reassembler
            await self.fragment_reassembler.stop()
            
            # Notify connection status
            await self.message_router.route_connection_status(False)
            
            logger.info("Meshtastic gateway stopped")
            
        except (ConnectionError, OSError, RuntimeError, asyncio.CancelledError) as e:
            logger.warning(f"Error stopping gateway: {e}")
    
    async def _refresh_device_data(self) -> None:
        """Refresh node data from the connected device."""
        try:
            channels = await self.meshtastic_client.get_channel_info()
            if channels:
                logger.info(f"Refreshed {len(channels)} channels from device")
            
            nodes = self.meshtastic_client.get_node_list()
            if nodes:
                for node in nodes:
                    if 'node_id' not in node and 'id' in node:
                        node['node_id'] = node['id']
                    if 'node_id' in node:
                        await self.node_store.upsert_node(node)
                logger.info(f"Refreshed {len(nodes)} nodes")
            
            await self.message_router.route_message({
                'message_type': 'data_refresh',
                'timestamp': datetime.now().isoformat(),
                'channels_count': len(channels) if channels else 0,
                'nodes_count': len(nodes) if nodes else 0
            })
        except (ConnectionError, OSError, RuntimeError, AttributeError) as e:
            logger.warning(f"Error refreshing device data: {e}")

    async def _manage_connection(self) -> None:
        """Background task to manage Meshtastic connection persistently.
        
        Keeps the TCP connection open for the lifetime of the session.
        On connection loss, retries every 10 seconds and refreshes data on reconnect.
        """
        was_previously_connected = False
        
        while self.running:
            try:
                if not self.meshtastic_client.is_connected():
                    if was_previously_connected:
                        logger.warning("Connection lost. Attempting reconnect...")
                        await self.message_router.route_connection_status(False, {
                            'error': 'Connection lost',
                            'host': self.settings.meshtastic.host,
                            'port': self.settings.meshtastic.port,
                            'reconnecting': True
                        })
                    
                    logger.info("Attempting to connect to Meshtastic device")
                    success = await self.meshtastic_client.connect(
                        timeout=self.settings.meshtastic.connection_timeout
                    )
                    
                    if success:
                        node_info = await self.meshtastic_client.get_node_info()
                        await self.message_router.route_connection_status(True, node_info)
                        was_previously_connected = True
                        self._connection_ready.set()
                        
                        await self.meshtastic_client.flush_pending_packets()
                        await self._refresh_device_data()
                        
                        logger.info("Connected to Meshtastic device")
                    else:
                        await self.message_router.route_connection_status(False, {
                            'error': 'Connection failed',
                            'host': self.settings.meshtastic.host,
                            'port': self.settings.meshtastic.port,
                            'reconnecting': self.auto_reconnect
                        })
                        self._connection_ready.set()
                        
                        if self.auto_reconnect:
                            logger.info(f"Reconnecting in {self.reconnect_delay}s")
                            await asyncio.sleep(self.reconnect_delay)
                        else:
                            break
                else:
                    await asyncio.sleep(CONNECTION_CHECK_INTERVAL)
                
            except asyncio.CancelledError:
                break
            except (ConnectionError, OSError, TimeoutError, RuntimeError) as e:
                logger.warning(f"Connection error in management loop: {e}")
                await self.message_router.route_error(
                    'connection_error', str(e),
                    {'host': self.settings.meshtastic.host, 'port': self.settings.meshtastic.port}
                )
                
                if self.auto_reconnect:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    break
            except Exception as e:  # Broad: keep loop alive for unexpected errors
                logger.warning(f"Unexpected error in connection management: {e}")
                await self.message_router.route_error(
                    'connection_error', str(e),
                    {'host': self.settings.meshtastic.host, 'port': self.settings.meshtastic.port}
                )
                
                if self.auto_reconnect:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    break
    
    async def _ensure_connected(self) -> bool:
        """Wait for initial connection and reconnect if needed.
        
        Returns True if connected, False if connection failed.
        """
        try:
            await asyncio.wait_for(self._connection_ready.wait(), timeout=20)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for initial connection - proceeding anyway")
        
        if not self.meshtastic_client.is_connected():
            logger.info("Not connected - attempting reconnect before sending")
            success = await self.meshtastic_client.connect(
                timeout=self.settings.meshtastic.connection_timeout
            )
            if not success:
                await self.message_router.route_error(
                    'send_error', 'Not connected to Meshtastic device. Reconnection failed.'
                )
                return False
            logger.info("Reconnected successfully")
        return True

    async def send_text_message(self, text: str, to_node: Optional[str] = None,
                               channel: int = 0, want_ack: bool = False) -> Dict[str, Any]:
        """
        Send a text message through the gateway.
        
        Uses the existing persistent TCP connection. If the connection is lost,
        attempts to reconnect before sending.
        
        Args:
            text: Message text to send
            to_node: Target node ID (None for broadcast)
            channel: Channel number
            want_ack: Whether to request acknowledgment
            
        Returns:
            dict with 'success' and 'packet_id' keys, or False on failure
        """
        try:
            if not await self._ensure_connected():
                return False
            
            result = await self.meshtastic_client.send_text_message(
                text, to_node, channel, want_ack
            )
            
            # result is either {'success': True, 'packet_id': <id>} or False
            if result and isinstance(result, dict) and result.get('success'):
                packet_id = result.get('packet_id')
                
                # Store our own message (but do NOT route to WebSocket clients -
                # the browser already displays sent messages from the REST response.
                # (Messages are stored client-side in localStorage.
                # Routing here would cause a duplicate "self" message in the UI.)
                
                logger.info(f"Sent text message: '{text[:50]}{'...' if len(text) > 50 else ''}' (packetId={packet_id})")
                return {'success': True, 'packet_id': packet_id}
            else:
                await self.message_router.route_error(
                    'send_error', 'Failed to send text message'
                )
                return False
            
        except (ConnectionError, OSError, RuntimeError, TypeError) as e:
            logger.warning(f"Error sending text message: {e}")
            await self.message_router.route_error('send_error', str(e))
            return False
    
    async def _send_one_segment(self, segment: str, index: int, total: int,
                                to_node: Optional[str], channel: int,
                                use_binary: bool) -> Optional[int]:
        """Send a single image segment and notify progress.
        
        Returns:
            packet_id on success, None on failure.
        """
        if use_binary:
            result = await self.meshtastic_client.send_binary_message(
                data=segment.encode('utf-8'),
                to_node=to_node, channel=channel,
                portnum=PortNum.PRIVATE_APP, want_ack=True
            )
        else:
            result = await self.meshtastic_client.send_text_message(
                text=segment, to_node=to_node,
                channel=channel, want_ack=True
            )
        
        send_ok = result and isinstance(result, dict) and result.get('success')
        packet_id = result.get('packet_id') if isinstance(result, dict) else None
        
        if not send_ok:
            logger.warning(f"Failed to send segment {index + 1}/{total}")
            await self.message_router.route_error(
                'send_error', f'Failed to send segment {index + 1}/{total}'
            )
            return None
        
        # Notify progress (messages stored client-side in localStorage)
        await self.message_router.route_message({
            'message_type': 'send_progress',
            'segment_index': index,
            'total_segments': total,
            'progress_percent': ((index + 1) / total) * 100,
            'packet_id': packet_id,
            'timestamp': datetime.now().isoformat()
        })
        
        return packet_id

    async def send_image_segments(self, segments: List[str], to_node: Optional[str] = None,
                                 channel: int = 0, delay_ms: int = 3000,
                                 send_method: str = 'text') -> bool:
        """
        Send image segments with wantAck=True and minimum 3s spacing.
        
        Args:
            segments: List of image message segments (text format)
            to_node: Target node ID (None for broadcast)
            channel: Channel number
            delay_ms: Delay between segments in milliseconds (minimum 3000)
            send_method: 'text' or 'binary' (BINARY_MESSAGE_APP portnum 256)
            
        Returns:
            True if all segments sent successfully
        """
        try:
            if not await self._ensure_connected():
                return False
            
            actual_delay = max(delay_ms, 3000)
            use_binary = send_method == 'binary'
            success_count = 0
            
            for i, segment in enumerate(segments):
                packet_id = await self._send_one_segment(
                    segment, i, len(segments), to_node, channel, use_binary
                )
                if packet_id is not None:
                    success_count += 1
                
                # Wait between segments (skip after last)
                if i < len(segments) - 1:
                    logger.info(f"Waiting {actual_delay}ms before next segment ({i+2}/{len(segments)})")
                    await asyncio.sleep(actual_delay / 1000.0)
            
            # Send completion status
            await self.message_router.route_message({
                'message_type': 'send_complete',
                'segments_sent': success_count,
                'total_segments': len(segments),
                'success': success_count == len(segments),
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"Sent {success_count}/{len(segments)} image segments")
            return success_count == len(segments)
            
        except (ConnectionError, OSError, RuntimeError, TypeError) as e:
            logger.warning(f"Error sending image segments: {e}")
            await self.message_router.route_error('send_error', str(e))
            return False
    
    async def get_node_list(self) -> List[Dict[str, Any]]:
        """Get list of all known nodes."""
        try:
            nodes = self.meshtastic_client.get_node_list()
            logger.info(f"Retrieved {len(nodes)} nodes from client")
            return nodes
        except (AttributeError, RuntimeError, ConnectionError) as e:
            logger.warning(f"Error in gateway get_node_list: {e}")
            return []
    
    async def get_fragments(self) -> List[Dict[str, Any]]:
        """Get status of all active fragments."""
        return await self.fragment_reassembler.get_all_fragments()
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        connected = self.meshtastic_client.is_connected()
        
        status = {
            'connected': connected,
            'host': self.settings.meshtastic.host,
            'port': self.settings.meshtastic.port,
            'auto_reconnect': self.auto_reconnect
        }
        
        if connected:
            node_info = await self.meshtastic_client.get_node_info()
            status.update(node_info)
        
        return status
    
    async def get_favorite_nodes(self) -> List[Dict[str, Any]]:
        """Get favorite nodes."""
        try:
            return await self.node_store.get_favorites()
        except (OSError, RuntimeError, KeyError) as e:
            logger.warning(f"Error getting favorite nodes: {e}")
            return []
    
    async def set_node_favorite(self, node_id: str, is_favorite: bool = True) -> bool:
        """Set node favorite status."""
        try:
            return await self.node_store.set_favorite(node_id, is_favorite)
        except (OSError, RuntimeError, KeyError) as e:
            logger.warning(f"Error setting node favorite: {e}")
            return False
    
    async def get_channels(self) -> List[Dict[str, Any]]:
        """Get channel configuration directly from the live device."""
        try:
            if self.meshtastic_client.is_connected():
                device_channels = await self.meshtastic_client.get_channel_info()
                logger.info(f"Retrieved {len(device_channels)} channels from device")
                return device_channels
            
            logger.warning("Cannot get channels - not connected to device")
            return []
            
        except (AttributeError, ConnectionError, RuntimeError) as e:
            logger.warning(f"Error getting channels: {e}")
            return []
    
    async def refresh_channels(self) -> bool:
        """Request fresh channel configuration from device."""
        try:
            if self.meshtastic_client.is_connected():
                logger.info("Requesting channel configuration refresh from device")
                await self.meshtastic_client.request_channel_update()
                
                # Give device time to respond, then re-fetch
                await asyncio.sleep(2)
                
                device_channels = await self.meshtastic_client.get_channel_info()
                logger.info(f"Channel refresh completed - {len(device_channels)} channels")
                return True
            else:
                logger.warning("Cannot refresh channels - not connected to device")
                return False
        except (ConnectionError, OSError, RuntimeError, AttributeError) as e:
            logger.warning(f"Error refreshing channels: {e}")
            return False
    
    async def get_device_settings(self) -> Dict[str, Any]:
        """Get device configuration settings."""
        try:
            if self.meshtastic_client.is_connected():
                return await self.meshtastic_client.get_device_settings()
            else:
                logger.warning("Cannot get device settings - not connected to device")
                return {}
        except (AttributeError, ConnectionError, RuntimeError) as e:
            logger.warning(f"Error getting device settings: {e}")
            return {}
    
    async def refresh_device_info(self) -> bool:
        """Request fresh device and node information."""
        try:
            if self.meshtastic_client.is_connected():
                # Request node info update
                await self.meshtastic_client.request_node_update()
                
                # Request channel update
                await self.meshtastic_client.request_channel_update()
                
                return True
            else:
                logger.warning("Cannot refresh device info - not connected to device")
                return False
        except (ConnectionError, OSError, RuntimeError, AttributeError) as e:
            logger.warning(f"Error refreshing device info: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get combined gateway and database statistics."""
        try:
            db_stats = await self.database.get_stats()
            return {
                **db_stats,
                'connected': self.meshtastic_client.is_connected(),
                'host': getattr(self.meshtastic_client, 'host', 'unknown'),
                'port': getattr(self.meshtastic_client, 'port', 'unknown')
            }
        except (OSError, RuntimeError, AttributeError) as e:
            logger.warning(f"Error getting stats: {e}")
            return {}