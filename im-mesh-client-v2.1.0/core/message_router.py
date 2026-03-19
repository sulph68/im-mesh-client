"""
Message router for distributing messages to appropriate handlers.

Routes messages to WebSocket clients, storage, and other components.
"""

import asyncio
import logging
import json
import base64
from typing import Dict, Any, List, Set, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

class MessageRouter:
    """
    Central message routing system.
    
    Distributes messages to WebSocket clients, database storage,
    and other registered handlers based on message type and routing rules.
    
    Maintains a rolling buffer of recent messages so clients can
    fetch any messages missed during a WebSocket disconnection.
    """
    
    # Maximum number of recent messages to keep in buffer
    MAX_RECENT_MESSAGES = 200
    
    def __init__(self):
        self.websocket_clients: Set[Any] = set()  # WebSocket connections
        self.message_handlers: Dict[str, List[Callable]] = {}
        self.broadcast_handlers: List[Callable] = []
        self._recent_messages: List[Dict[str, Any]] = []  # Rolling buffer
        
    def register_websocket(self, websocket) -> None:
        """Register a WebSocket client for message broadcasting."""
        self.websocket_clients.add(websocket)
        logger.debug(f"WebSocket client registered, total: {len(self.websocket_clients)}")
    
    def unregister_websocket(self, websocket) -> None:
        """Unregister a WebSocket client."""
        self.websocket_clients.discard(websocket)
        logger.debug(f"WebSocket client unregistered, remaining: {len(self.websocket_clients)}")
    
    def register_handler(self, message_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a handler for specific message types.
        
        Args:
            message_type: Type of message to handle
            handler: Callable that processes the message
        """
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        
        self.message_handlers[message_type].append(handler)
        logger.info(f"Registered handler for '{message_type}' (total: {len(self.message_handlers[message_type])})")
    
    def subscribe(self, message_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to messages of a specific type (alias for register_handler).
        
        Args:
            message_type: Type of message to subscribe to
            handler: Callable that processes the message
        """
        self.register_handler(message_type, handler)
    
    def clear_handlers(self) -> None:
        """Clear all registered handlers. Used when WebSocket reconnects to avoid stale closures."""
        count = sum(len(v) for v in self.message_handlers.values()) + len(self.broadcast_handlers)
        self.message_handlers.clear()
        self.broadcast_handlers.clear()
        if count > 0:
            logger.info(f"Cleared {count} message handlers")
    
    def register_broadcast_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a handler that receives all messages."""
        self.broadcast_handlers.append(handler)
        logger.debug("Registered broadcast handler")
    
    async def route_message(self, message: Dict[str, Any]) -> None:
        """
        Route a message to appropriate handlers.
        
        Args:
            message: Message dictionary to route
        """
        try:
            message_type = message.get('message_type', 'unknown')
            
            # Add routing metadata
            message['routed_at'] = datetime.now().isoformat()
            
            # Buffer user-facing message types for missed-message retrieval
            if message_type in ('text', 'binary', 'binary_complete', 'ack',
                                'image_complete', 'node_update', 'position_update'):
                self._recent_messages.append(message)
                if len(self._recent_messages) > self.MAX_RECENT_MESSAGES:
                    self._recent_messages = self._recent_messages[-self.MAX_RECENT_MESSAGES:]
            
            # Route to specific handlers
            handler_count = len(self.message_handlers.get(message_type, []))
            if message_type in ('text', 'binary', 'binary_complete', 'ack'):
                logger.info(f"Routing {message_type} from {message.get('from_node', '?')} "
                           f"(handlers={handler_count})")
            
            if message_type in self.message_handlers:
                for i, handler in enumerate(self.message_handlers[message_type]):
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:  # Broad: unknown handler signatures
                        logger.warning(f"Error in message handler for {message_type}: {e}", exc_info=True)
            elif message_type in ('text', 'binary', 'binary_complete', 'ack'):
                logger.warning(f"No handlers for message_type={message_type} - message buffered for later delivery")
            
            # Route to broadcast handlers
            for handler in self.broadcast_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:  # Broad: unknown handler signatures
                    logger.warning(f"Error in broadcast handler: {e}")
            
            # Route to WebSocket clients (legacy path - usually empty)
            await self._broadcast_to_websockets(message)
            
            logger.debug(f"Routed {message_type} message from {message.get('from_node', 'unknown')}")
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error routing message: {e}", exc_info=True)
    
    async def route_text_message(self, message: Dict[str, Any]) -> None:
        """Route a text message."""
        message['message_type'] = 'text'
        await self.route_message(message)
    
    async def route_binary_message(self, message: Dict[str, Any]) -> None:
        """Route a binary message."""
        message['message_type'] = 'binary'
        await self.route_message(message)
    
    async def route_binary_complete(self, message: Dict[str, Any]) -> None:
        """Route a completed binary message."""
        message['message_type'] = 'binary_complete'
        await self.route_message(message)
    
    async def route_node_update(self, node_info: Dict[str, Any]) -> None:
        """Route a node information update."""
        message = {
            'message_type': 'node_update',
            'node_info': node_info,
            'timestamp': datetime.now().isoformat()
        }
        await self.route_message(message)
    
    async def route_fragment_progress(self, fragment_key: str, fragment_info: Dict[str, Any]) -> None:
        """Route fragment progress update."""
        message = {
            'message_type': 'fragment_progress',
            'fragment_key': fragment_key,
            'fragment_info': {
                'fragment_id': fragment_info['fragment_id'],
                'from_node': fragment_info['from_node'],
                'total_segments': fragment_info['total_segments'],
                'received_count': fragment_info['received_count'],
                'progress_percent': (fragment_info['received_count'] / fragment_info['total_segments']) * 100,
                'updated_at': fragment_info['updated_at'].isoformat()
            },
            'timestamp': datetime.now().isoformat()
        }
        await self.route_message(message)
    
    async def route_connection_status(self, connected: bool, info: Dict[str, Any] = None) -> None:
        """Route connection status update."""
        message = {
            'message_type': 'connection_status',
            'connected': connected,
            'connection_info': info or {},
            'timestamp': datetime.now().isoformat()
        }
        await self.route_message(message)
    
    async def route_error(self, error_type: str, error_message: str, details: Dict[str, Any] = None) -> None:
        """Route error message."""
        message = {
            'message_type': 'error',
            'error_type': error_type,
            'error_message': error_message,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        await self.route_message(message)
    
    async def _broadcast_to_websockets(self, message: Dict[str, Any]) -> None:
        """Broadcast message to all connected WebSocket clients."""
        if not self.websocket_clients:
            return
        
        # Prepare message for WebSocket transmission
        ws_message = {
            'type': message.get('message_type', 'unknown'),
            'data': message,
            'timestamp': datetime.now().isoformat()
        }
        
        # Serialize safely (bytes -> base64, datetime -> isoformat)
        def _serialize(obj):
            if isinstance(obj, bytes):
                return base64.b64encode(obj).decode('ascii')
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Not serializable: {type(obj)}")
        
        try:
            message_text = json.dumps(ws_message, default=_serialize)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize broadcast message: {e}")
            return
        
        # Send to all connected clients
        disconnected_clients = set()
        
        for websocket in self.websocket_clients.copy():
            try:
                await websocket.send_text(message_text)
            except (ConnectionError, RuntimeError) as e:
                logger.warning(f"Failed to send message to WebSocket client: {e}")
                disconnected_clients.add(websocket)
        
        # Remove disconnected clients
        for websocket in disconnected_clients:
            self.websocket_clients.discard(websocket)
        
        if disconnected_clients:
            logger.info(f"Removed {len(disconnected_clients)} disconnected WebSocket clients")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        return {
            'websocket_clients': len(self.websocket_clients),
            'message_handlers': {
                msg_type: len(handlers) 
                for msg_type, handlers in self.message_handlers.items()
            },
            'broadcast_handlers': len(self.broadcast_handlers),
            'recent_message_buffer': len(self._recent_messages)
        }
    
    def get_messages_since(self, since_iso: str) -> List[Dict[str, Any]]:
        """
        Return buffered messages routed after the given ISO timestamp.
        Used by clients to retrieve messages missed during a WebSocket disconnect.
        
        Args:
            since_iso: ISO-format timestamp string (e.g. from routed_at)
            
        Returns:
            List of message dicts routed after the given time
        """
        result = []
        for msg in self._recent_messages:
            routed_at = msg.get('routed_at', '')
            if routed_at > since_iso:
                result.append(msg)
        return result
    
    async def broadcast_system_message(self, message: str, level: str = 'info') -> None:
        """Broadcast a system message to all clients."""
        system_message = {
            'message_type': 'system',
            'level': level,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        await self.route_message(system_message)