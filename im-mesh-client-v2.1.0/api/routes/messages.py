"""Message sending routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends

from core.session_manager import Session
from api.models import SendTextMessageRequest, SendImageRequest, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["messages"])


def create_message_routes(get_session_dep) -> APIRouter:
    """Create message sending routes."""

    @router.post("/messages/send")
    async def send_text_message(
        request: SendTextMessageRequest,
        session: Session = Depends(get_session_dep)
    ):
        """Send a text message through the session."""
        try:
            result = await session.gateway.send_text_message(
                text=request.text,
                to_node=request.to_node,
                channel=request.channel,
                want_ack=request.want_ack
            )

            if result and isinstance(result, dict) and result.get('success'):
                return MessageResponse(
                    success=True,
                    message="Message sent successfully",
                    data={'packet_id': result.get('packet_id')}
                )
            elif result:
                return MessageResponse(success=True, message="Message sent successfully")
            else:
                return MessageResponse(success=False, message="Failed to send message")

        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error sending message: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/messages/send-image")
    async def send_image_segments(
        request: SendImageRequest,
        session: Session = Depends(get_session_dep)
    ):
        """Send image segments through the session."""
        try:
            success = await session.gateway.send_image_segments(
                segments=request.segments,
                to_node=request.to_node,
                channel=request.channel,
                delay_ms=request.delay_ms,
                send_method=request.send_method
            )
            return MessageResponse(
                success=success,
                message="Image segments sent successfully" if success else "Failed to send some segments"
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error sending image segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
