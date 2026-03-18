"""
Value objects and data classes for the Meshtastic Image Encoder/Decoder.
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from .config import IMAGE_SIZES, SUPPORTED_BIT_DEPTHS, COMPRESSION_METHODS


@dataclass(frozen=True)
class ImageDimensions:
    """Value object representing image dimensions."""
    width: int
    height: int
    
    @classmethod
    def from_string(cls, size_string: str) -> 'ImageDimensions':
        """Create ImageDimensions from string like '128x64'."""
        if size_string not in IMAGE_SIZES:
            raise ValueError(f"Unsupported image size: {size_string}")
        width, height = IMAGE_SIZES[size_string]
        return cls(width, height)
    
    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio."""
        return self.width / self.height
    
    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class CompressionConfig:
    """Configuration for compression settings."""
    method: str
    bit_depth: int
    use_heatshrink: bool = True
    
    def __post_init__(self):
        if self.method not in COMPRESSION_METHODS:
            raise ValueError(f"Unsupported compression method: {self.method}")
        if self.bit_depth not in SUPPORTED_BIT_DEPTHS:
            raise ValueError(f"Unsupported bit depth: {self.bit_depth}")
    
    @property
    def method_code(self) -> str:
        """Get method code for message format."""
        code = COMPRESSION_METHODS[self.method]
        return code.lower() if self.use_heatshrink else code.upper()
    
    @property
    def quantization_levels(self) -> int:
        """Get number of quantization levels."""
        return 2 ** self.bit_depth


@dataclass
class PreparationStats:
    """Statistics from image preparation process."""
    original_size: Tuple[int, int]
    target_size: Tuple[int, int]
    original_mode: str
    bit_depth: int
    quantization_levels: int


@dataclass
class CompressionStats:
    """Statistics from compression process."""
    compression_method: str
    compression_ratio: float
    unique_tiles: Optional[int]
    total_tiles: Optional[int]
    base64_encoded_chars: int
    uses_heatshrink: bool = True
    
    @property
    def tile_efficiency(self) -> Optional[float]:
        """Calculate tile compression efficiency."""
        if self.unique_tiles is None or self.total_tiles is None:
            return None
        return self.unique_tiles / self.total_tiles if self.total_tiles > 0 else 0


@dataclass
class SegmentConfig:
    """Configuration for message segmentation."""
    max_length: int = 220
    
    def __post_init__(self):
        if not (200 <= self.max_length <= 300):
            raise ValueError("Segment length must be between 200 and 300 characters")
    
    @property
    def max_data_per_segment(self) -> int:
        """Calculate maximum data length per segment (excluding header)."""
        # Reserve space for header: IMG{w}x{h}:{method}{mode}:{seg}/{total}:
        # Approximate overhead: 25 characters
        return self.max_length - 25