"""Shared Pydantic models for API requests and responses."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from core.constants import DEFAULT_SEGMENT_LENGTH, MIN_SEGMENT_LENGTH, MAX_SEGMENT_LENGTH, DEFAULT_MESHTASTIC_PORT


class CreateSessionRequest(BaseModel):
    meshtastic_host: str = Field(default="localhost")
    meshtastic_port: int = Field(default=DEFAULT_MESHTASTIC_PORT, ge=0, le=65535)
    session_name: Optional[str] = None
    session_id: Optional[str] = None
    connection_type: str = Field(default="tcp")  # "tcp" or "serial"
    serial_port: Optional[str] = None  # e.g., "/dev/ttyUSB0", "COM3"

class SendTextMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=228)
    to_node: Optional[str] = None
    channel: int = Field(default=0, ge=0, le=7)
    want_ack: bool = False

class SendImageRequest(BaseModel):
    segments: List[str] = Field(..., min_items=1)
    to_node: Optional[str] = None
    channel: int = Field(default=0, ge=0, le=7)
    delay_ms: int = Field(default=3000, ge=100, le=10000)
    send_method: str = Field(default="text")

class DecodeSegmentsRequest(BaseModel):
    segments: List[str] = Field(..., min_items=1)

class EncodeImageRequest(BaseModel):
    bit_depth: int = Field(default=1, ge=1, le=4)
    image_width: int = Field(default=64, ge=8, le=256)
    image_height: int = Field(default=64, ge=8, le=256)
    mode: str = Field(default="rle_nibble_xor")
    segment_length: int = Field(default=DEFAULT_SEGMENT_LENGTH, ge=MIN_SEGMENT_LENGTH, le=MAX_SEGMENT_LENGTH)

class MessageResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
