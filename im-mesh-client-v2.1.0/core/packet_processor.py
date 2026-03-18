"""
Packet processing mixin for MeshtasticClientReal.

Handles received packet normalization, decoded payload processing,
message type dispatch, self-echo filtering, and deduplication.

This is a mixin class - it accesses self.interface, self._processed_packet_ids,
self._processed_packet_id_set, self._event_loop, self._pending_packets,
self.packet_callbacks via the host class.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from .constants import PortNum, PORTNUM_MAP

logger = logging.getLogger(__name__)


class PacketProcessorMixin:
    """Mixin providing packet receive processing and dispatch."""

    def _pubsub_receive_handler(self, packet, interface=None):
        """pypubsub callback for meshtastic.receive (and all subtopics).

        This is a BOUND METHOD stored as an instance attribute, ensuring pypubsub
        holds a strong reference and it won't be garbage collected.
        Called from the Meshtastic library's publishingThread.

        CRITICAL: pypubsub is a process-global singleton. When multiple sessions
        each create a TCPInterface, ALL subscribers receive ALL packets from ALL
        interfaces. We MUST filter by interface identity to only process packets
        from our own connection.

        Additionally, pypubsub topic hierarchy can deliver the same packet multiple
        times (once per matching topic level). We dedup by packet 'id' field.
        """
        try:
            if not isinstance(packet, dict):
                return

            # CRITICAL: Filter by interface - only process packets from OUR connection.
            if interface is not None and self.interface is not None:
                if interface is not self.interface:
                    return  # Packet from a different session's interface

            # Dedup: pypubsub delivers same packet for parent + child topics
            pkt_id = packet.get('id')
            if pkt_id is not None:
                if pkt_id in self._processed_packet_id_set:
                    return  # Already processed this packet
                # Add to both structures; deque auto-evicts oldest when full
                if len(self._processed_packet_ids) == self._processed_packet_ids.maxlen:
                    evicted = self._processed_packet_ids[0]
                    self._processed_packet_id_set.discard(evicted)
                self._processed_packet_ids.append(pkt_id)
                self._processed_packet_id_set.add(pkt_id)

            from_id = packet.get('fromId', '?')
            portnum = packet.get('decoded', {}).get('portnum', '?')
            logger.debug(f"PUBSUB RX: from={from_id} portnum={portnum}")
            self._on_receive(packet, interface)
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            logger.warning(f"Data error in _pubsub_receive_handler: {e}")
        except Exception as e:  # Broad fallback: catch-all for unknown packet formats
            logger.exception(f"Unexpected error in _pubsub_receive_handler: {e}")

    def _pubsub_connection_handler(self, interface, topic=None):
        """pypubsub callback for meshtastic.connection.established."""
        try:
            # Filter by interface - only process events from our connection
            if interface is not None and self.interface is not None:
                if interface is not self.interface:
                    return
            logger.info("PUBSUB: Connection established")
            self._on_connection(interface, topic)
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error in _pubsub_connection_handler: {e}")

    def _pubsub_connection_lost_handler(self, interface):
        """pypubsub callback for meshtastic.connection.lost."""
        try:
            # Filter by interface - only process events from our connection
            if interface is not None and self.interface is not None:
                if interface is not self.interface:
                    return
            logger.warning("PUBSUB: Connection lost")
            self._on_connection_lost(interface)
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error in _pubsub_connection_lost_handler: {e}")

    def _on_receive(self, packet, interface=None):
        """Handle received packet from Meshtastic device via pypubsub.

        IMPORTANT: This is called from the Meshtastic library's publishing thread,
        NOT from the asyncio event loop. We must use run_coroutine_threadsafe to
        dispatch async work to the main event loop.
        """
        try:
            if not isinstance(packet, dict):
                logger.warning(f"Unexpected packet type: {type(packet)}")
                return

            # Filter echoed packets from self (except ROUTING_APP for ACK tracking)
            if self._is_self_echo(packet):
                return

            # Build normalized packet dict
            packet_dict = self._build_packet_dict(packet)

            # Process decoded payload into typed message
            decoded = packet.get('decoded', {})
            if decoded:
                self._process_decoded_payload(packet_dict, packet, decoded)

            # Dispatch to async callback pipeline
            self._dispatch_packet(packet_dict)

        except (KeyError, AttributeError, TypeError, ValueError) as e:
            logger.warning(f"Data error handling received packet: {e}")
        except Exception as e:  # Broad fallback: catch-all for unknown packet formats
            logger.exception(f"Unexpected error handling received packet: {e}")

    def _get_my_node_id(self) -> str:
        """Get our own node ID string (e.g. '!3d8309d0')."""
        if not self.interface:
            return None
        # Try myInfo first
        if hasattr(self.interface, 'myInfo') and self.interface.myInfo:
            my_info = self.interface.myInfo
            my_node_num = my_info.get('my_node_num') if isinstance(my_info, dict) else getattr(my_info, 'my_node_num', None)
            if my_node_num is not None:
                return f"!{my_node_num:08x}"
        # Fall back to localNode
        if hasattr(self.interface, 'localNode') and self.interface.localNode:
            local_node = self.interface.localNode
            if hasattr(local_node, 'nodeNum'):
                return f"!{local_node.nodeNum:08x}"
        return None

    def _is_self_echo(self, packet: dict) -> bool:
        """Check if packet is an echo of our own transmission.

        Returns True if packet should be filtered out. ROUTING_APP from self
        is allowed through for ACK tracking.
        """
        from_id = packet.get('fromId', '')
        my_node_id = self._get_my_node_id()

        if not my_node_id or from_id != my_node_id:
            return False

        decoded = packet.get('decoded', {})
        portnum = decoded.get('portnum', '') if isinstance(decoded, dict) else ''
        if portnum == 'ROUTING_APP' or portnum == PortNum.ROUTING_APP:
            logger.info(f"Allowing ROUTING_APP from self ({from_id}) for ack tracking")
            return False

        logger.debug(f"Ignoring echoed packet from self ({from_id}) portnum={portnum}")
        return True

    def _build_packet_dict(self, packet: dict) -> dict:
        """Build a normalized packet dictionary from raw Meshtastic packet."""
        from_id = packet.get('fromId', '')
        packet_dict = {
            'from': packet.get('from'),
            'to': packet.get('to'),
            'from_node': from_id,
            'id': packet.get('id'),
            'rx_time': datetime.now().isoformat(),
            'channel': packet.get('channel', 0),
            'hop_limit': packet.get('hopLimit'),
            'want_ack': packet.get('wantAck', False),
            'rx_snr': packet.get('rxSnr'),
            'rx_rssi': packet.get('rxRssi'),
        }

        # Resolve sender name from node database
        if from_id and self.interface and hasattr(self.interface, 'nodes'):
            node_info = self.interface.nodes.get(from_id, {})
            if isinstance(node_info, dict) and 'user' in node_info:
                user = node_info['user']
                if isinstance(user, dict):
                    packet_dict['from_name'] = user.get('longName', from_id)
                    packet_dict['from_short'] = user.get('shortName', '')

        return packet_dict

    def _process_decoded_payload(self, packet_dict: dict, packet: dict, decoded: dict):
        """Process decoded payload and set message_type and type-specific fields."""
        portnum_str = decoded.get('portnum', '')
        payload = decoded.get('payload', b'')
        portnum_int = self._portnum_to_int(portnum_str)
        from_id = packet_dict.get('from_node', '')

        packet_dict['decoded'] = {
            'portnum': portnum_int,
            'payload': payload,
            'want_response': decoded.get('wantResponse', False)
        }

        if portnum_str == 'TEXT_MESSAGE_APP' or portnum_int == PortNum.TEXT_MESSAGE_APP:
            self._handle_text_message(packet_dict, decoded, payload, from_id, packet.get('channel', 0))
        elif portnum_str == 'PRIVATE_APP' or portnum_int == PortNum.PRIVATE_APP:
            self._handle_binary_message(packet_dict, payload, from_id)
        elif portnum_str == 'POSITION_APP' or portnum_int == PortNum.POSITION_APP:
            packet_dict['message_type'] = 'position'
            if 'position' in decoded:
                packet_dict['decoded']['position_data'] = decoded['position']
        elif portnum_str == 'NODEINFO_APP' or portnum_int == PortNum.NODEINFO_APP:
            packet_dict['message_type'] = 'node_info'
            if 'user' in decoded:
                packet_dict['decoded']['user_info'] = decoded['user']
        elif portnum_str == 'ROUTING_APP' or portnum_int == PortNum.ROUTING_APP:
            self._handle_routing_message(packet_dict, decoded, packet, from_id)
        elif portnum_str == 'TELEMETRY_APP' or portnum_int == PortNum.TELEMETRY_APP:
            packet_dict['message_type'] = 'telemetry'
        else:
            packet_dict['message_type'] = f'portnum_{portnum_int}'
            logger.debug(f"RX portnum={portnum_str} from {from_id}")

    def _handle_text_message(self, packet_dict: dict, decoded: dict, payload, from_id: str, channel: int):
        """Process a TEXT_MESSAGE_APP packet."""
        text = decoded.get('text', '')
        if not text and isinstance(payload, bytes):
            try:
                text = payload.decode('utf-8')
            except (UnicodeDecodeError, AttributeError):
                text = str(payload)
        packet_dict['decoded']['text'] = text
        packet_dict['decoded_text'] = text
        packet_dict['message_type'] = 'text'
        logger.info(f"RX TEXT from {from_id} ch={channel} len={len(text)}: {text[:80]}")

    def _handle_binary_message(self, packet_dict: dict, payload, from_id: str):
        """Process a PRIVATE_APP (binary) packet."""
        packet_dict['decoded']['binary_data'] = payload.hex() if isinstance(payload, bytes) else str(payload)
        packet_dict['message_type'] = 'binary'
        logger.info(f"RX BINARY from {from_id}: {len(payload) if isinstance(payload, bytes) else 0} bytes")

    def _handle_routing_message(self, packet_dict: dict, decoded: dict, packet: dict, from_id: str):
        """Process a ROUTING_APP (ACK/NAK) packet."""
        packet_dict['message_type'] = 'routing'

        # Extract requestId from multiple possible locations
        request_id = decoded.get('requestId') or decoded.get('request_id')
        if not request_id:
            request_id = packet.get('requestId') or packet.get('request_id')

        routing = decoded.get('routing', {})
        if not request_id and routing:
            if isinstance(routing, dict):
                request_id = routing.get('requestId') or routing.get('request_id')
            else:
                request_id = getattr(routing, 'requestId', None) or getattr(routing, 'request_id', None)

        # Extract and normalize error reason
        if isinstance(routing, dict):
            error_reason = routing.get('errorReason', 'NONE')
        else:
            error_reason = getattr(routing, 'errorReason', 'NONE') if routing else 'NONE'

        if hasattr(error_reason, 'name'):
            error_reason = error_reason.name
        elif isinstance(error_reason, int):
            error_reason = 'NONE' if error_reason == 0 else f'ERROR_{error_reason}'

        # protobuf default 0 means unset
        if request_id == 0:
            request_id = None

        packet_dict['decoded']['request_id'] = request_id
        packet_dict['decoded']['error_reason'] = str(error_reason)
        packet_dict['decoded']['ack_received'] = str(error_reason) in ('NONE', '0')

        logger.info(f"RX ROUTING from {from_id}: requestId={request_id} error={error_reason}")
        logger.debug(f"ROUTING raw: requestId_val={decoded.get('requestId')} routing_keys={list(routing.keys()) if isinstance(routing, dict) else 'N/A'}")

    def _dispatch_packet(self, packet_dict: dict):
        """Dispatch processed packet to async callback pipeline."""
        if self._event_loop and self._event_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._notify_callbacks(packet_dict), self._event_loop)
            def _on_future_done(f):
                exc = f.exception()
                if exc:
                    logger.error(f"Error dispatching packet callback: {exc}")
            future.add_done_callback(_on_future_done)
        else:
            msg_type = packet_dict.get('message_type', 'unknown')
            if msg_type in ('text', 'binary', 'routing'):
                self._pending_packets.append(packet_dict)
                logger.warning(f"Queued {msg_type} packet (no event loop yet), queue size: {len(self._pending_packets)}")
            else:
                logger.debug(f"Dropped {msg_type} packet (no event loop, startup race condition)")

    def _portnum_to_int(self, portnum) -> int:
        """Convert portnum (string or int) to integer."""
        if isinstance(portnum, int):
            return portnum
        return PORTNUM_MAP.get(str(portnum), PortNum.UNKNOWN_APP)
