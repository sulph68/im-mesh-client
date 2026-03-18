"""
API package for Meshtastic Web Client.

REST and WebSocket endpoints for multi-tenant communication.
"""

from .rest_api_multitenant import create_rest_api
from .websocket_api_multitenant import WebSocketAPI

__all__ = ['create_rest_api', 'WebSocketAPI']
