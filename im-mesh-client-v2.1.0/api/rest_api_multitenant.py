"""
REST API for Multi-Tenant Meshtastic Web Client.

Provides session-aware HTTP endpoints with isolated node connections.
Each session maintains separate databases and Meshtastic connections.

Routes are organized into APIRouter modules:
- sessions: Session lifecycle (create, list, delete)
- messages: Text and image message sending
- nodes: Node list, favorites, details
- channels: Channels, device settings, connection status
- encoding: Image encode/decode
"""

import re
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Cookie, Header, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from core.session_manager import SessionManager, Session
from api.websocket_api_multitenant import WebSocketAPI
from config.settings import Settings
from api.models import MessageResponse

# Route modules
from api.routes.sessions import create_session_routes
from api.routes.messages import create_message_routes
from api.routes.nodes import create_node_routes
from api.routes.channels import create_channel_routes
from api.routes.encoding import create_encoding_routes

logger = logging.getLogger(__name__)


def create_session_dependency(session_manager: SessionManager):
    """Create session dependency factory for route injection."""
    _UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

    async def get_session(
        session_id: Optional[str] = Cookie(None),
        x_session_id: Optional[str] = Header(None)
    ) -> Session:
        session_id = x_session_id or session_id
        if not session_id:
            raise HTTPException(status_code=400, detail="No session ID provided")
        if not _UUID_RE.match(session_id):
            raise HTTPException(status_code=400, detail="Invalid session ID format")
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    return get_session


def create_rest_api(session_manager: SessionManager, websocket_api: WebSocketAPI, settings: Settings, lifespan=None) -> FastAPI:
    """Create FastAPI application with session-aware endpoints."""

    app = FastAPI(
        title="Im Mesh Client API",
        description="Multi-tenant REST API for Meshtastic communication",
        version="2.1.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create shared session dependency
    get_session_dep = create_session_dependency(session_manager)

    # Register route modules
    app.include_router(create_session_routes(session_manager))
    app.include_router(create_message_routes(get_session_dep))
    app.include_router(create_node_routes(get_session_dep))
    app.include_router(create_channel_routes(session_manager, get_session_dep))
    app.include_router(create_encoding_routes(get_session_dep))

    # Health endpoint (no session required)
    @app.get("/api/health")
    async def health_check():
        """Basic health check endpoint."""
        return MessageResponse(
            success=True,
            message="Service healthy",
            data={
                "timestamp": datetime.now().isoformat(),
                "version": "2.1.0"
            }
        )

    # Mount static files
    app.mount("/static", StaticFiles(directory="web/static"), name="static")

    # Serve main page
    @app.get("/", response_class=HTMLResponse)
    async def read_index():
        """Serve the main web interface."""
        try:
            with open("web/static/index.html") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Web interface not found")

    # WebSocket endpoint
    @app.websocket("/ws/")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time communication."""
        await websocket_api.handle_websocket(websocket)

    return app
