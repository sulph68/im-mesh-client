"""Session management routes."""

import logging
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from core.session_manager import SessionManager
from core.constants import SESSION_COOKIE_MAX_AGE
from api.models import CreateSessionRequest, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])


def create_session_routes(session_manager: SessionManager) -> APIRouter:
    """Create session management routes."""

    @router.post("/sessions")
    async def create_session(request: CreateSessionRequest):
        """Create a new session for a Meshtastic node, or reuse an existing one."""
        try:
            # Determine connection type
            connection_type = request.connection_type or "tcp"
            serial_port = None

            if connection_type == "serial":
                # Serial connection: extract port from serial_port field or host
                serial_port = request.serial_port
                if not serial_port and request.meshtastic_host.startswith("serial://"):
                    serial_port = request.meshtastic_host[len("serial://"):]
                if not serial_port:
                    raise HTTPException(status_code=400, detail="Serial port is required for serial connections")
                # Use serial port as the "host" for session lookup
                host = f"serial://{serial_port}"
                port = 0
            else:
                # TCP connection
                host = request.meshtastic_host.strip()
                if not host or '/' in host or '\\' in host or '..' in host or ';' in host:
                    raise HTTPException(status_code=400, detail="Invalid hostname")
                if len(host) > 253:
                    raise HTTPException(status_code=400, detail="Hostname too long")
                port = request.meshtastic_port

            existing_id = session_manager.find_session_by_host_port(host, port)
            reused = existing_id is not None

            suggested_id = None
            if not reused and request.session_id:
                if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', request.session_id):
                    suggested_id = request.session_id

            session_id = await session_manager.create_session(
                meshtastic_host=host,
                meshtastic_port=port,
                session_id=suggested_id,
                connection_type=connection_type,
                serial_port=serial_port
            )

            session = await session_manager.get_session(session_id)
            if session and not reused:
                await session.start()

            connected = False
            if session:
                try:
                    status = await session.gateway.get_connection_status()
                    connected = status.get('connected', False)
                except (ConnectionError, OSError, RuntimeError, AttributeError):
                    pass  # Best-effort connection status check

            response = JSONResponse(content=MessageResponse(
                success=True,
                message="Session restored" if reused else "Session created successfully",
                data={
                    "session_id": session_id,
                    "meshtastic_host": host,
                    "meshtastic_port": port,
                    "connection_type": connection_type,
                    "reused": reused,
                    "connected": connected
                }
            ).dict())
            response.set_cookie("session_id", session_id, httponly=True, max_age=SESSION_COOKIE_MAX_AGE)
            return response

        except HTTPException:
            raise
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error creating session: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sessions")
    async def list_sessions():
        """List all active sessions."""
        try:
            sessions = await session_manager.list_sessions()
            return MessageResponse(
                success=True,
                message="Sessions retrieved successfully",
                data={"sessions": sessions, "count": len(sessions)}
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error listing sessions: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sessions/{session_id}")
    async def get_session_info(session_id: str):
        """Get information about a specific session."""
        try:
            session = await session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            connection_status = await session.gateway.get_connection_status()
            return MessageResponse(
                success=True,
                message="Session info retrieved successfully",
                data={
                    "session_id": session_id,
                    "connection": connection_status,
                    "created_at": session.created_at.isoformat(),
                    "last_accessed": session.last_accessed.isoformat()
                }
            )
        except HTTPException:
            raise
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting session info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/sessions/{session_id}")
    async def close_session(session_id: str, delete_data: bool = False):
        """Close a specific session."""
        try:
            success = await session_manager.close_session(session_id, delete_data=delete_data)
            if success:
                return MessageResponse(
                    success=True,
                    message="Session deleted" if delete_data else "Session closed successfully"
                )
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        except HTTPException:
            raise
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error closing session: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
