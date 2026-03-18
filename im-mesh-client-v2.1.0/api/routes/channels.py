"""Channel and device routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends, Cookie, Header
from typing import Optional

from core.session_manager import SessionManager, Session
from api.models import MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["channels"])


def create_channel_routes(session_manager: SessionManager, get_session_dep) -> APIRouter:
    """Create channel and device management routes."""

    @router.get("/connection")
    async def get_connection_status(
        session_id: Optional[str] = Cookie(None),
        x_session_id: Optional[str] = Header(None)
    ):
        """Get connection status for the session."""
        try:
            sid = x_session_id or session_id
            if not sid:
                raise HTTPException(status_code=400, detail="No session ID provided")
            session = await session_manager.get_session(sid)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            status = await session.gateway.get_connection_status()
            return MessageResponse(success=True, message="Connection status retrieved successfully", data=status)
        except HTTPException:
            raise
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting connection status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/channels")
    async def get_channels(session: Session = Depends(get_session_dep)):
        """Get channel configuration for the session."""
        try:
            channels = await session.gateway.get_channels()
            return MessageResponse(
                success=True,
                message="Channels retrieved successfully",
                data={"channels": channels, "count": len(channels)}
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting channels: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/channels/refresh")
    async def refresh_channels(session: Session = Depends(get_session_dep)):
        """Request fresh channel configuration from device."""
        try:
            success = await session.gateway.refresh_channels()
            return MessageResponse(
                success=success,
                message="Channel refresh requested" if success else "Failed to request channel refresh"
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error refreshing channels: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/device/refresh")
    async def refresh_device_info(session: Session = Depends(get_session_dep)):
        """Request fresh device and node information."""
        try:
            success = await session.gateway.refresh_device_info()
            return MessageResponse(
                success=success,
                message="Device refresh requested" if success else "Failed to request device refresh"
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error refreshing device info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/device/settings")
    async def get_device_settings(session: Session = Depends(get_session_dep)):
        """Get device configuration settings."""
        try:
            settings = await session.gateway.get_device_settings()
            return MessageResponse(
                success=True,
                message="Device settings retrieved successfully",
                data={"settings": settings}
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting device settings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/fragments")
    async def get_fragments(session: Session = Depends(get_session_dep)):
        """Get active fragment status."""
        try:
            fragments = await session.gateway.get_fragments()
            return MessageResponse(
                success=True,
                message="Fragments retrieved successfully",
                data={"fragments": fragments, "count": len(fragments)}
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting fragments: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
