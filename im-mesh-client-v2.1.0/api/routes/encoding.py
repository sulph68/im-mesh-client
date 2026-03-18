"""Image encoding and decoding routes."""

import json
import logging
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form

from core.session_manager import Session
from encoding.encoder_adapter import encoder_adapter, EncodingError
from encoding.decoder_adapter import decoder_adapter, DecodingError
from api.models import DecodeSegmentsRequest, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["encoding"])


def create_encoding_routes(get_session_dep) -> APIRouter:
    """Create image encoding/decoding routes."""

    @router.post("/encode-image")
    async def encode_image_file(
        file: UploadFile = File(...),
        encoding_params: str = Form(...),
        session: Session = Depends(get_session_dep)
    ):
        """Encode uploaded image for transmission."""
        try:
            params = json.loads(encoding_params)

            if not file.content_type or not file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="File must be an image")

            file_data = await file.read()

            try:
                result = encoder_adapter.encode_image_from_data(file_data, params)
                return MessageResponse(
                    success=True,
                    message=f"Image encoded into {len(result['segments'])} segments",
                    data=result
                )
            except EncodingError as e:
                raise HTTPException(status_code=400, detail=f"Encoding failed: {str(e)}")

        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid encoding parameters JSON")
        except HTTPException:
            raise
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error encoding image: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/decode-segments")
    async def decode_image_segments(
        request: DecodeSegmentsRequest,
        session: Session = Depends(get_session_dep)
    ):
        """Decode image segments back into an image."""
        try:
            result = decoder_adapter.decode_segments(request.segments)

            if result['success']:
                return MessageResponse(
                    success=True,
                    message="Image decoded successfully",
                    data={'image_data': result['image_data'], 'stats': result['stats']}
                )
            else:
                return MessageResponse(
                    success=False,
                    message=f"Decoding failed: {result.get('error', 'Unknown error')}",
                    data=None
                )

        except DecodingError as e:
            raise HTTPException(status_code=400, detail=f"Decoding error: {str(e)}")
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error decoding image segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
