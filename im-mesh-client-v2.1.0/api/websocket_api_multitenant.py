"""
WebSocket API for Multi-Tenant Meshtastic Web Client.

Provides real-time updates for individual sessions with proper isolation.
Each WebSocket connection is associated with a specific session.
"""

import json
import logging
import re
import base64
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

from core.session_manager import SessionManager, Session

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


def _json_serialize(obj):
    """Custom JSON serializer that handles bytes, datetime, and other non-serializable types."""
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode('ascii')
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

class WebSocketAPI:
    """
    WebSocket API with session support.
    
    Manages WebSocket connections and routes real-time updates
    to appropriate session subscribers.
    """
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        
        # Track connections by session
        self.session_connections: Dict[str, Set[WebSocket]] = {}
        
        # Track session for each connection
        self.connection_sessions: Dict[WebSocket, str] = {}
        
        # Track last successful WS send time per session for flush dedup
        self._last_ws_send_time: Dict[str, str] = {}
    
    async def _negotiate_auth(self, websocket: WebSocket) -> Optional[str]:
        """
        Negotiate session authentication from the first WebSocket message.
        
        Returns:
            Validated session_id string, or None if auth failed (connection closed).
        """
        try:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get('type') != 'auth' or 'session_id' not in message:
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': 'Authentication required: send session_id'
                }))
                await websocket.close()
                return None
            
            sid = message['session_id']
            
            if not isinstance(sid, str) or not _UUID_RE.match(sid):
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': 'Invalid session ID format'
                }))
                await websocket.close()
                return None
            
            return sid
            
        except (json.JSONDecodeError, KeyError):
            await websocket.send_text(json.dumps({
                'type': 'error',
                'message': 'Invalid authentication message'
            }))
            await websocket.close()
            return None
        except (WebSocketDisconnect, Exception) as e:
            logger.info(f"WebSocket disconnected during auth: {e}")
            return None

    async def handle_websocket(self, websocket: WebSocket, session_id: Optional[str] = None):
        """
        Handle WebSocket connection for a specific session.
        
        Args:
            websocket: WebSocket connection
            session_id: Session ID to associate with connection
        """
        await websocket.accept()
        
        # If no session ID provided, negotiate from first message
        if not session_id:
            session_id = await self._negotiate_auth(websocket)
            if not session_id:
                return
        
        # Verify session exists
        session = await self.session_manager.get_session(session_id)
        if not session:
            await websocket.send_text(json.dumps({
                'type': 'error',
                'message': 'Session not found'
            }))
            await websocket.close()
            return
        
        # Register connection with session
        self._add_connection(session_id, websocket)
        
        try:
            # Send initial connection confirmation
            await websocket.send_text(json.dumps({
                'type': 'connected',
                'session_id': session_id,
                'timestamp': datetime.now().isoformat()
            }))
            
            # Setup message router callback for this session
            await self._setup_session_callbacks(session, websocket)
            
            # Send auth_success so the JS client triggers loadInitialData()
            await websocket.send_text(json.dumps({
                'type': 'auth_success',
                'session_id': session_id,
                'timestamp': datetime.now().isoformat()
            }))
            
            # Flush any buffered messages that arrived while no WS was connected.
            # This ensures the client receives messages that were routed between
            # the last WS disconnect and this new connection.
            await self._flush_buffered_messages(session, session_id)
            
            # Listen for messages from client
            await self._handle_client_messages(websocket, session)
            
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session {session_id}")
        except (ConnectionError, RuntimeError) as e:
            logger.warning(f"WebSocket error for session {session_id}: {e}")
        finally:
            # Cleanup connection
            self._remove_connection(session_id, websocket)
    
    def _add_connection(self, session_id: str, websocket: WebSocket):
        """Add WebSocket connection to session tracking."""
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        
        self.session_connections[session_id].add(websocket)
        self.connection_sessions[websocket] = session_id
        
        logger.info(f"Added WebSocket connection for session {session_id}")
    
    def _remove_connection(self, session_id: str, websocket: WebSocket):
        """Remove WebSocket connection from session tracking."""
        if session_id in self.session_connections:
            self.session_connections[session_id].discard(websocket)
            
            # Remove empty session sets
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
        
        self.connection_sessions.pop(websocket, None)
        
        logger.info(f"Removed WebSocket connection for session {session_id}")
    
    async def _setup_session_callbacks(self, session: Session, websocket: WebSocket):
        """Setup callbacks for session events.
        
        Subscribes to all message types that the packet_handler and message_router emit.
        Clears existing handlers first to avoid accumulation from WebSocket reconnects.
        """
        message_router = session.gateway.message_router
        
        # Clear stale handlers from previous WebSocket connections.
        message_router.clear_handlers()
        
        def _make_ws_callback(ws_type: str, log_detail: bool = False):
            """Create a WebSocket forwarding callback for a message type."""
            async def callback(data: Dict[str, Any]):
                try:
                    if log_detail:
                        msg_type = data.get('message_type', 'unknown')
                        from_node = data.get('from_node', 'unknown')
                        preview = (data.get('decoded_text', '') or '')[:50]
                        logger.info(f"WS routing {msg_type} from {from_node} to session {session.id}: {preview}")
                    await self._send_to_session(session.id, {
                        'type': ws_type,
                        'data': data
                    })
                except Exception as e:  # Broad: unknown user callback types
                    logger.error(f"Error in {ws_type} callback: {e}")
            return callback
        
        # Map: router event -> (WS type, log detail)
        # NOTE: 'text_sent' and 'binary_sent' are NOT subscribed here.
        # The browser JS already displays sent messages from the REST API response.
        subscriptions = [
            ('text',              'message',           True),
            ('binary',            'message',           True),
            ('binary_complete',   'binary_complete',   False),
            ('image_complete',    'image_complete',    False),
            ('ack',               'ack',               False),
            ('node_update',       'node_update',       False),
            ('position_update',   'node_update',       False),
            ('fragment_progress', 'fragment_progress', False),
            ('connection_status', 'connection_status', False),
        ]
        
        for router_event, ws_type, log_detail in subscriptions:
            message_router.subscribe(router_event, _make_ws_callback(ws_type, log_detail))
        
        logger.info(f"Session {session.id} WebSocket callbacks registered ({len(subscriptions)} types)")
    
    async def _flush_buffered_messages(self, session: Session, session_id: str):
        """
        Deliver buffered messages that arrived while no WebSocket was connected.
        
        The MessageRouter keeps a rolling buffer of recent messages. When a new
        WebSocket connects, we send any buffered text/binary/ack messages that
        arrived after the last successful WebSocket delivery, so the client
        receives messages it missed during disconnection.
        """
        try:
            message_router = session.gateway.message_router
            
            # Get messages since the last successful WS send for this session
            since = self._last_ws_send_time.get(session_id)
            if since:
                buffered = message_router.get_messages_since(since)
            else:
                # No previous WS delivery tracked - send ALL buffered messages.
                # The buffer is capped at 200 messages, so this is bounded.
                buffered = list(message_router._recent_messages)
            
            if not buffered:
                return
            
            # Filter to user-facing message types only
            user_types = ('text', 'binary', 'binary_complete', 'ack', 'image_complete')
            user_msgs = [m for m in buffered if m.get('message_type') in user_types]
            
            if not user_msgs:
                return
            
            # Map message_type to WS type (same mapping as subscriptions)
            type_map = {
                'text': 'message',
                'binary': 'message',
                'binary_complete': 'binary_complete',
                'image_complete': 'image_complete',
                'ack': 'ack',
            }
            
            logger.info(f"Flushing {len(user_msgs)} buffered messages to session {session_id}")
            
            for msg in user_msgs:
                ws_type = type_map.get(msg.get('message_type'), 'message')
                await self._send_to_session(session_id, {
                    'type': ws_type,
                    'data': msg
                })
            
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Error flushing buffered messages: {e}")
    
    async def _handle_client_messages(self, websocket: WebSocket, session: Session):
        """Handle messages from WebSocket client."""
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                message_type = message.get('type')
                
                if message_type == 'ping':
                    # Respond to ping
                    await websocket.send_text(json.dumps({
                        'type': 'pong',
                        'timestamp': datetime.now().isoformat()
                    }))
                
                elif message_type == 'request_update':
                    # Send current session status
                    await self._send_session_status(websocket, session)
                
                elif message_type == 'subscribe':
                    # Handle subscription requests
                    event_type = message.get('event')
                    if event_type:
                        logger.info(f"WebSocket subscribed to {event_type} for session {session.id}")
                
                else:
                    logger.warning(f"Unknown WebSocket message type: {message_type}")
                
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received from WebSocket client")
            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected for session {session.id}")
                break
            except (ConnectionError, RuntimeError) as e:
                # Code 1000 = normal close, not an error
                if '1000' in str(e) or '1001' in str(e):
                    logger.info(f"WebSocket closed normally for session {session.id}")
                else:
                    logger.warning(f"Error handling WebSocket message: {e}")
                break
    
    async def _send_session_status(self, websocket: WebSocket, session: Session):
        """Send current session status to WebSocket client."""
        try:
            # Get current session status
            connection_status = await session.gateway.get_connection_status()
            stats = await session.gateway.get_stats()
            
            await websocket.send_text(json.dumps({
                'type': 'status_update',
                'data': {
                    'session_id': session.id,
                    'connection': connection_status,
                    'stats': stats,
                    'timestamp': datetime.now().isoformat()
                }
            }))
            
        except (ConnectionError, RuntimeError, TypeError) as e:
            logger.warning(f"Error sending session status: {e}")
    
    async def _send_to_session(self, session_id: str, message: Dict[str, Any]):
        """Send message to all WebSocket connections for a session."""
        msg_type = message.get('type', '?')
        if session_id not in self.session_connections:
            logger.debug(f"No WS connections for session {session_id}, "
                        f"message type={msg_type} buffered (no active WS)")
            return
        
        connections = self.session_connections[session_id]
        if not connections:
            logger.debug(f"Empty WS connection set for session {session_id}, "
                        f"message type={msg_type} buffered (no active WS)")
            return
        
        # Add timestamp to message
        message['timestamp'] = datetime.now().isoformat()
        
        # Serialize with custom handler for bytes/datetime
        try:
            message_json = json.dumps(message, default=_json_serialize)
        except (TypeError, ValueError) as e:
            logger.warning(f"Error serializing WebSocket message: {e}")
            return
        
        # Send to all connections for this session
        disconnected_connections = []
        sent_ok = False
        for websocket in self.session_connections[session_id]:
            try:
                await websocket.send_text(message_json)
                sent_ok = True
            except (ConnectionError, RuntimeError) as e:
                logger.warning(f"Error sending WebSocket message: {e}")
                disconnected_connections.append(websocket)
        
        # Track last successful send time for buffer flush dedup
        if sent_ok:
            self._last_ws_send_time[session_id] = datetime.now().isoformat()
        
        # Clean up disconnected connections
        for websocket in disconnected_connections:
            self._remove_connection(session_id, websocket)
    
    async def broadcast_to_all_sessions(self, message: Dict[str, Any]):
        """Broadcast message to all active sessions."""
        for session_id in list(self.session_connections.keys()):
            await self._send_to_session(session_id, message)
    
    async def get_session_connection_count(self, session_id: str) -> int:
        """Get number of active WebSocket connections for a session."""
        return len(self.session_connections.get(session_id, set()))
    
    async def get_total_connection_count(self) -> int:
        """Get total number of active WebSocket connections."""
        return sum(len(connections) for connections in self.session_connections.values())
    
    async def disconnect_session(self, session_id: str):
        """Disconnect all WebSocket connections for a session."""
        if session_id in self.session_connections:
            connections = list(self.session_connections[session_id])
            
            for websocket in connections:
                try:
                    await websocket.send_text(json.dumps({
                        'type': 'session_closed',
                        'message': 'Session has been closed'
                    }))
                    await websocket.close()
                except (ConnectionError, RuntimeError) as e:
                    logger.warning(f"Error closing WebSocket: {e}")
            
            # Clear all connections for this session
            self.session_connections.pop(session_id, None)
            
            # Clean up connection tracking
            for websocket in connections:
                self.connection_sessions.pop(websocket, None)
    
    async def shutdown(self):
        """Shutdown all WebSocket connections."""
        logger.info("Shutting down WebSocket API...")
        
        # Close all connections
        all_connections = []
        for connections in self.session_connections.values():
            all_connections.extend(connections)
        
        for websocket in all_connections:
            try:
                await websocket.send_text(json.dumps({
                    'type': 'shutdown',
                    'message': 'Server is shutting down'
                }))
                await websocket.close()
            except (ConnectionError, RuntimeError) as e:
                logger.warning(f"Error closing WebSocket during shutdown: {e}")
        
        # Clear all tracking
        self.session_connections.clear()
        self.connection_sessions.clear()
        
        logger.info("WebSocket API shutdown complete")