"""
Encoder adapter for integrating mesh_image library.

Provides a clean interface to the image encoding functionality while
isolating the mesh_image codec implementation.
"""

import sys
import re
import logging
from pathlib import Path
from typing import Dict, Any, List
from PIL import Image
import io
import base64

# Check if heatshrink2 is available
try:
    import heatshrink2  # noqa: F401
    HAS_HEATSHRINK = True
except ImportError:
    HAS_HEATSHRINK = False

# Import mesh_image library - check bundled copy first, then external sibling
_project_root = Path(__file__).parent.parent
_bundled_path = _project_root / "mesh_image"
_external_path = _project_root.parent / "mesh_image"

if (_bundled_path / "run" / "encoder.py").exists():
    sys.path.insert(0, str(_bundled_path))
elif (_external_path / "run" / "encoder.py").exists():
    sys.path.insert(0, str(_external_path))

try:
    from run.encoder import encode_image_simple, encode_image_file
    ENCODER_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Failed to import mesh_image encoder: {e}")
    ENCODER_AVAILABLE = False

logger = logging.getLogger(__name__)

if not HAS_HEATSHRINK:
    logger.warning("heatshrink2 not installed - image segments will use non-heatshrink encoding")

class EncodingError(Exception):
    """Exception raised during image encoding."""
    pass

class EncoderAdapter:
    """
    Adapter for mesh_image encoding library.
    
    Provides a clean interface for encoding images into Meshtastic-compatible
    message segments while isolating the underlying codec implementation.
    """
    
    def __init__(self):
        self.available = ENCODER_AVAILABLE
    
    @staticmethod
    def _fix_segments_no_heatshrink(segments: List[str]) -> List[str]:
        """
        Fix segment headers when heatshrink2 is not installed.
        
        The mesh_image library defaults use_heatshrink=True and uses lowercase
        method codes (e.g. x1, r1, t1) to indicate heatshrink compression.
        When heatshrink2 is not available, the library silently skips compression
        but still uses lowercase codes. This causes receivers to attempt
        heatshrink decompression on uncompressed data, resulting in decode errors.
        
        This method converts lowercase method codes to uppercase to correctly
        indicate that heatshrink compression was NOT applied.
        """
        if HAS_HEATSHRINK:
            return segments
        
        fixed = []
        for seg in segments:
            # Match: IMG{w}x{h}:{method_code}{bit_depth}:{rest}
            match = re.match(r'^(IMG\d+x\d+:)([a-z])(\d+:.+)$', seg)
            if match:
                prefix = match.group(1)
                method = match.group(2).upper()
                rest = match.group(3)
                fixed.append(f"{prefix}{method}{rest}")
            else:
                fixed.append(seg)
        return fixed
        
    def encode_image_from_file(self, file_path: str, encoding_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encode image from file path.
        
        Args:
            file_path: Path to image file
            encoding_settings: Dictionary with encoding parameters
            
        Returns:
            Dictionary containing:
            - segments: List of message segments
            - stats: Encoding statistics
            - preview_data: Base64 encoded preview image
            
        Raises:
            EncodingError: If encoding fails
        """
        if not self.available:
            raise EncodingError("Image encoder not available")
            
        try:
            # Extract settings with defaults
            bit_depth = encoding_settings.get('bit_depth', 1)
            width = encoding_settings.get('image_width', 64)
            height = encoding_settings.get('image_height', 64)
            compression_method = encoding_settings.get('mode', 'rle_nibble_xor')
            segment_length = encoding_settings.get('segment_length', 200)
            
            # Use mesh_image library to encode
            result = encode_image_file(
                image_path=file_path,
                bit_depth=bit_depth,
                width=width,
                height=height,
                compression_method=compression_method,
                segment_length=segment_length
            )
            
            # Fix segment headers if heatshrink is not available
            segments = self._fix_segments_no_heatshrink(result['segments'])
            
            return {
                'segments': segments,
                'stats': {
                    'segment_count': len(segments),
                    'total_bytes': sum(len(seg.encode('utf-8')) for seg in segments),
                    'compression_ratio': result['compression_stats']['compression_ratio'],
                    'compression_method': compression_method,
                    'image_dimensions': f"{width}x{height}",
                    'bit_depth': bit_depth
                },
                'preview_data': result.get('processed_image', ''),
                'original_preview': result.get('original_image', '')
            }
            
        except (ValueError, TypeError, IOError, OSError) as e:
            logger.error(f"Image encoding failed: {e}")
            raise EncodingError(f"Failed to encode image: {e}")
    
    def encode_image_from_data(self, image_data: bytes, encoding_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encode image from binary data.
        
        Args:
            image_data: Binary image data
            encoding_settings: Dictionary with encoding parameters
            
        Returns:
            Dictionary containing segments, stats, and preview data
            
        Raises:
            EncodingError: If encoding fails
        """
        if not self.available:
            raise EncodingError("Image encoder not available")
            
        try:
            # Load image from data
            image = Image.open(io.BytesIO(image_data))
            
            # Extract settings
            bit_depth = encoding_settings.get('bit_depth', 1)
            width = encoding_settings.get('image_width', 64)
            height = encoding_settings.get('image_height', 64)
            compression_method = encoding_settings.get('mode', 'rle_nibble_xor')
            segment_length = encoding_settings.get('segment_length', 200)
            
            # Clamp segment_length to mesh_image library's valid range (200-300)
            segment_length = max(200, min(300, segment_length))
            
            # Encode using mesh_image library
            segments = encode_image_simple(
                image=image,
                bit_depth=bit_depth,
                width=width,
                height=height,
                compression_method=compression_method,
                segment_length=segment_length
            )
            
            # Fix segment headers if heatshrink is not available
            segments = self._fix_segments_no_heatshrink(segments)
            
            # Generate original preview (resized input image)
            preview_image = image.resize((width, height))
            preview_buffer = io.BytesIO()
            preview_image.save(preview_buffer, format='PNG')
            preview_data = base64.b64encode(preview_buffer.getvalue()).decode('ascii')
            
            # Generate decoded preview (actual encoded result decoded back)
            # This shows the user exactly what the receiver will see
            decoded_preview = preview_data  # fallback to original resize
            try:
                from run.decoder import decode_segments_simple
                decoded_image = decode_segments_simple(segments)
                if decoded_image:
                    decoded_buffer = io.BytesIO()
                    decoded_image.save(decoded_buffer, format='PNG')
                    decoded_preview = base64.b64encode(decoded_buffer.getvalue()).decode('ascii')
            except (ImportError, ValueError, TypeError, IOError) as dec_err:
                logger.warning(f"Could not generate decoded preview: {dec_err}")
            
            return {
                'segments': segments,
                'stats': {
                    'segment_count': len(segments),
                    'total_bytes': sum(len(seg.encode('utf-8')) for seg in segments),
                    'compression_method': compression_method,
                    'image_dimensions': f"{width}x{height}",
                    'bit_depth': bit_depth,
                    'original_size': len(image_data)
                },
                'preview_data': preview_data,
                'decoded_preview': decoded_preview,
                'original_preview': preview_data
            }
            
        except (ValueError, TypeError, IOError, OSError) as e:
            logger.error(f"Image encoding from data failed: {e}")
            raise EncodingError(f"Failed to encode image from data: {e}")
    
    def get_encoding_info(self, encoding_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get information about encoding settings without actually encoding.
        
        Args:
            encoding_settings: Dictionary with encoding parameters
            
        Returns:
            Dictionary with encoding information
        """
        compression_methods = {
            'tile_rle': 'Tile-based RLE compression (good for logos/diagrams)',
            'rle_nibble': 'RLE with nibble packing (optimal for photos)',
            'rle_nibble_xor': 'RLE nibble with XOR (best for patterns)'
        }
        
        bit_depth_info = {
            1: '2 levels (black/white)',
            2: '4 levels (grayscale)',
            4: '16 levels (detailed grayscale)'
        }
        
        method = encoding_settings.get('mode', 'rle_nibble')
        bit_depth = encoding_settings.get('bit_depth', 1)
        width = encoding_settings.get('image_width', 64)
        height = encoding_settings.get('image_height', 64)
        
        # Estimate segment count (rough approximation)
        pixel_count = width * height
        estimated_bytes = (pixel_count * bit_depth) // 8
        segment_length = encoding_settings.get('segment_length', 220)
        estimated_segments = max(1, (estimated_bytes * 4 // 3) // segment_length)  # Base64 expansion
        
        return {
            'available': self.available,
            'method_description': compression_methods.get(method, 'Unknown method'),
            'bit_depth_description': bit_depth_info.get(bit_depth, 'Unknown bit depth'),
            'estimated_segments': estimated_segments,
            'estimated_total_chars': estimated_segments * segment_length,
            'pixel_count': pixel_count,
            'settings_valid': self._validate_settings(encoding_settings)
        }
    
    def _validate_settings(self, settings: Dict[str, Any]) -> bool:
        """Validate encoding settings."""
        try:
            # Check required fields and valid ranges
            bit_depth = settings.get('bit_depth', 1)
            if bit_depth not in [1, 2, 4]:
                return False
                
            method = settings.get('mode', 'rle_nibble')
            if method not in ['tile_rle', 'rle_nibble', 'rle_nibble_xor']:
                return False
                
            width = settings.get('image_width', 64)
            height = settings.get('image_height', 64)
            if not (8 <= width <= 256 and 8 <= height <= 256):
                return False
                
            segment_length = settings.get('segment_length', 220)
            if not (50 <= segment_length <= 500):
                return False
                
            return True
            
        except (KeyError, TypeError, ValueError):
            return False

# Global encoder instance
encoder_adapter = EncoderAdapter()