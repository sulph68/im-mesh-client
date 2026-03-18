"""
Packet handler for interpreting and processing Meshtastic packets.

Handles different packet types and routes them appropriately.
"""

import logging
import base64
from datetime import datetime
from typing import Dict, Any, Optional
from .constants import PortNum, is_broadcast
from .fragment_reassembler import FragmentReassembler
from .message_router import MessageRouter
from storage.node_store import NodeStore
from encoding.decoder_adapter import decoder_adapter

logger = logging.getLogger(__name__)

class PacketHandler:
    """
    Handles interpretation and processing of Meshtastic packets.
    
    Routes different packet types (TEXT_MESSAGE_APP, BINARY_MESSAGE_APP, etc.)
    to appropriate handlers and manages fragment detection.
    """
    
    def __init__(self, node_store: NodeStore,
                 message_router: MessageRouter, fragment_reassembler: FragmentReassembler):
        self.node_store = node_store
        self.message_router = message_router
        self.fragment_reassembler = fragment_reassembler
        
    async def handle_packet(self, packet: Dict[str, Any]) -> None:
        """
        Main packet handling entry point.
        
        Args:
            packet: Raw packet data from Meshtastic device
        """
        try:
            # Extract basic packet info
            from_node = packet.get('from_node') or packet.get('from', 'unknown')
            to_node = packet.get('to')
            channel = packet.get('channel', 0)
            hop_limit = packet.get('hop_limit')
            want_ack = packet.get('want_ack', False)
            rx_snr = packet.get('rx_snr')
            rx_rssi = packet.get('rx_rssi')
            rx_time = packet.get('rx_time', datetime.now())
            from_name = packet.get('from_name')
            from_short = packet.get('from_short')
            
            # Convert numeric node IDs to hex strings
            if isinstance(from_node, int):
                from_node = f"!{from_node:08x}"
            if isinstance(to_node, int):
                to_node = f"!{to_node:08x}"
            
            # Update node last seen
            await self.node_store.mark_node_seen(from_node)
            
            # Extract decoded payload
            decoded = packet.get('decoded', {})
            if not decoded:
                logger.debug(f"Packet from {from_node} has no decoded payload")
                return
            
            portnum = decoded.get('portnum')
            payload = decoded.get('payload')
            
            if portnum is None:
                logger.debug(f"Packet from {from_node} has no portnum")
                return
            
            # Handle different port numbers
            if portnum == PortNum.TEXT_MESSAGE_APP:
                await self._handle_text_message(
                    from_node, to_node, channel, payload, rx_time, rx_snr, rx_rssi,
                    from_name=from_name
                )
            elif portnum == PortNum.PRIVATE_APP:
                await self._handle_binary_message(
                    from_node, to_node, channel, payload, rx_time, rx_snr, rx_rssi,
                    from_name=from_name
                )
            elif portnum == PortNum.POSITION_APP:
                await self._handle_position_update(from_node, decoded, rx_time)
            elif portnum == PortNum.NODEINFO_APP:
                await self._handle_node_info(from_node, decoded, rx_time)
            elif portnum == PortNum.ROUTING_APP:
                await self._handle_routing_packet(from_node, decoded, rx_time)
            else:
                logger.debug(f"Unhandled portnum {portnum} from {from_node}")
                
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            logger.error(f"Error handling packet: {e}")
    
    async def _handle_text_message(self, from_node: str, to_node: Optional[str],
                                  channel: int, payload, rx_time,
                                  rx_snr: Optional[float], rx_rssi: Optional[int],
                                  from_name: Optional[str] = None) -> None:
        """Handle text message packets."""
        try:
            # Decode text payload
            if isinstance(payload, bytes):
                text = payload.decode('utf-8', errors='ignore')
            elif isinstance(payload, str):
                # Might be hex-encoded - try to decode
                try:
                    text = bytes.fromhex(payload).decode('utf-8', errors='ignore')
                except ValueError:
                    text = payload
            else:
                text = str(payload)
            
            # Create message data
            message_data = {
                'timestamp': rx_time.isoformat() if hasattr(rx_time, 'isoformat') else str(rx_time),
                'from_node': from_node,
                'from_name': from_name or from_node,
                'to_node': to_node,
                'channel': channel,
                'portnum': PortNum.TEXT_MESSAGE_APP,
                'payload': base64.b64encode(payload).decode('ascii') if isinstance(payload, bytes) else str(payload),
                'message_type': 'text',
                'decoded_text': text,
                'rx_snr': rx_snr,
                'rx_rssi': rx_rssi,
                'is_broadcast': is_broadcast(to_node),
                'is_fragment': False
            }
            
            # Route to handlers (messages stored client-side in localStorage)
            await self.message_router.route_text_message(message_data)
            
            logger.info(f"Text message from {from_node} len={len(text)}: {text[:50]}{'...' if len(text) > 50 else ''}")
            
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
            logger.error(f"Error handling text message: {e}")
    
    async def _handle_binary_message(self, from_node: str, to_node: Optional[str],
                                   channel: int, payload, rx_time,
                                   rx_snr: Optional[float], rx_rssi: Optional[int],
                                   from_name: Optional[str] = None) -> None:
        """Handle binary message packets."""
        try:
            # Convert payload to string if needed
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8', errors='ignore')
            elif isinstance(payload, str):
                # Might be hex-encoded
                try:
                    payload_str = bytes.fromhex(payload).decode('utf-8', errors='ignore')
                except ValueError:
                    payload_str = payload
            else:
                payload_str = str(payload)
            
            # Check if this might be an image message fragment
            is_image_fragment = decoder_adapter.is_image_message(payload_str)
            
            # Determine if this is a fragment
            is_fragment, fragment_info = await self._detect_fragment(payload_str)
            
            # Create base message data
            message_data = {
                'timestamp': rx_time.isoformat() if hasattr(rx_time, 'isoformat') else str(rx_time),
                'from_node': from_node,
                'from_name': from_name or from_node,
                'to_node': to_node,
                'channel': channel,
                'portnum': PortNum.PRIVATE_APP,
                'payload': payload_str,
                'message_type': 'binary',
                'rx_snr': rx_snr,
                'rx_rssi': rx_rssi,
                'is_broadcast': is_broadcast(to_node),
                'is_fragment': is_fragment
            }
            
            # Add fragment information if detected
            if is_fragment and fragment_info:
                message_data.update({
                    'fragment_id': fragment_info['fragment_id'],
                    'fragment_total': fragment_info['total_segments'],
                    'fragment_index': fragment_info['segment_index']
                })
            
            # Handle fragments (messages stored client-side in localStorage)
            if is_fragment:
                # Process through fragment reassembler
                complete_message = await self.fragment_reassembler.process_fragment(message_data)
                
                if complete_message:
                    # Fragment is complete, try to decode if it's an image
                    if is_image_fragment:
                        await self._handle_complete_image_message(complete_message)
                    else:
                        await self.message_router.route_binary_complete(complete_message)
                
                # Also route the fragment itself
                await self.message_router.route_binary_message(message_data)
            else:
                # Single binary message
                await self.message_router.route_binary_message(message_data)
            
            logger.info(f"Binary message from {from_node} ({len(payload_str)} chars)"
                       f"{' [Fragment]' if is_fragment else ''}"
                       f"{' [Image]' if is_image_fragment else ''}")
            
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
            logger.error(f"Error handling binary message: {e}")
    
    async def _detect_fragment(self, payload: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Detect if payload is a fragment of a larger message.
        
        Args:
            payload: Message payload string
            
        Returns:
            Tuple of (is_fragment, fragment_info)
        """
        try:
            # Check for image message format (IMG{width}x{height}:...)
            if payload.startswith('IMG') and ':' in payload:
                parts = payload.split(':')
                if len(parts) >= 3:
                    # Parse segment info: {segment_index}/{total_segments}
                    segment_part = parts[2]
                    if '/' in segment_part:
                        segment_index_str, total_segments_str = segment_part.split('/')
                        try:
                            segment_index = int(segment_index_str)
                            total_segments = int(total_segments_str)
                            
                            if total_segments > 1:
                                # Generate fragment ID from the message header
                                fragment_id = f"{parts[0]}_{parts[1]}"  # IMG{dimensions}_{method}
                                
                                return True, {
                                    'fragment_id': fragment_id,
                                    'segment_index': segment_index,
                                    'total_segments': total_segments
                                }
                        except ValueError:
                            pass
            
            # Add other fragment detection patterns here
            
            return False, None
            
        except (ValueError, IndexError, TypeError) as e:
            logger.error(f"Error detecting fragment: {e}")
            return False, None
    
    async def _handle_complete_image_message(self, complete_message: Dict[str, Any]) -> None:
        """Handle a completed image message for decoding."""
        try:
            payload = complete_message.get('payload', '')
            
            # Split payload back into segments
            # This is a simplified approach - in reality, we'd need to properly
            # reconstruct the original segments from the concatenated payload
            segments = [payload]  # For now, treat as single segment
            
            # Try to decode the image
            decode_result = decoder_adapter.decode_segments(segments)
            
            if decode_result['success']:
                # Add decoded image data to the message
                complete_message['decoded_image'] = decode_result['image_data']
                complete_message['decode_stats'] = decode_result['stats']
                complete_message['message_type'] = 'image_complete'
                
                logger.info(f"Successfully decoded image from {complete_message['from_node']}")
            else:
                complete_message['decode_error'] = decode_result['error']
                logger.warning(f"Failed to decode image: {decode_result['error']}")
            
            # Route the complete image message
            await self.message_router.route_message(complete_message)
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error handling complete image message: {e}")
    
    async def _handle_position_update(self, from_node: str, decoded: Dict[str, Any], rx_time: datetime) -> None:
        """Handle position update packets."""
        try:
            # Extract position data
            latitude = decoded.get('latitude')
            longitude = decoded.get('longitude')
            altitude = decoded.get('altitude')
            
            if latitude is not None and longitude is not None:
                # Update node position
                await self.node_store.update_node_position(from_node, latitude, longitude, altitude)
                
                # Route position update
                position_data = {
                    'node_id': from_node,
                    'latitude': latitude,
                    'longitude': longitude,
                    'altitude': altitude,
                    'timestamp': rx_time
                }
                
                await self.message_router.route_message({
                    'message_type': 'position_update',
                    'position_data': position_data,
                    'timestamp': rx_time
                })
                
                logger.debug(f"Position update from {from_node}: {latitude}, {longitude}")
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error handling position update: {e}")
    
    async def _handle_node_info(self, from_node: str, decoded: Dict[str, Any], rx_time: datetime) -> None:
        """Handle node info packets."""
        try:
            # Extract node information
            user_info = decoded.get('user', {})
            
            node_data = {
                'node_id': from_node,
                'short_name': user_info.get('shortName'),
                'long_name': user_info.get('longName'),
                'hw_model': user_info.get('hwModel'),
                'macaddr': user_info.get('macaddr'),
                'last_seen': rx_time
            }
            
            # Update node information
            await self.node_store.upsert_node(node_data)
            
            # Route node update
            await self.message_router.route_node_update(node_data)
            
            logger.info(f"Node info update: {from_node} ({node_data.get('short_name', 'Unknown')})")
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error handling node info: {e}")
    
    async def _handle_routing_packet(self, from_node: str, decoded: Dict[str, Any], rx_time) -> None:
        """Handle routing packets (ack/nak responses).
        
        When we send a message with wantAck=True, the recipient (or mesh relay) sends
        back a ROUTING_APP packet with the original packet's ID as request_id.
        This lets us confirm delivery.
        """
        try:
            request_id = decoded.get('request_id')
            error_reason = decoded.get('error_reason', 'NONE')
            ack_received = decoded.get('ack_received', str(error_reason) == 'NONE')
            
            ack_data = {
                'message_type': 'ack',
                'from_node': from_node,
                'request_id': request_id,
                'error_reason': str(error_reason),
                'ack_received': ack_received,
                'timestamp': rx_time.isoformat() if hasattr(rx_time, 'isoformat') else str(rx_time)
            }
            
            # Route ack to WebSocket clients so the UI can update sent messages
            await self.message_router.route_message(ack_data)
            
            status = 'ACK' if ack_received else f'NAK ({error_reason})'
            logger.info(f"Routing {status} from {from_node} for packetId={request_id}")
            
        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"Error handling routing packet: {e}")