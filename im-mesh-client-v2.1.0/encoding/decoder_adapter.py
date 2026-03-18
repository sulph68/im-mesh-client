"""
Decoder adapter for integrating mesh_image library.

Provides a clean interface to decode Meshtastic image messages back into images.
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image
import io
import base64

# Import mesh_image library - check bundled copy first, then external sibling
_project_root = Path(__file__).parent.parent
_bundled_path = _project_root / "mesh_image"
_external_path = _project_root.parent / "mesh_image"

if (_bundled_path / "run" / "decoder.py").exists():
    sys.path.insert(0, str(_bundled_path))
elif (_external_path / "run" / "decoder.py").exists():
    sys.path.insert(0, str(_external_path))

try:
    from run.decoder import decode_segments_simple, decode_segments_with_stats
    DECODER_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Failed to import mesh_image decoder: {e}")
    DECODER_AVAILABLE = False

logger = logging.getLogger(__name__)

class DecodingError(Exception):
    """Exception raised during image decoding."""
    pass

class DecoderAdapter:
    """
    Adapter for mesh_image decoding library.
    
    Provides a clean interface for decoding Meshtastic message segments
    back into images while isolating the underlying codec implementation.
    """
    
    def __init__(self):
        self.available = DECODER_AVAILABLE
        
    def _clean_segments(self, segments: List[str]) -> List[str]:
        """
        Clean image segments before passing to the decoder.
        
        Strips whitespace from each segment. Removes any incorrectly-added
        base64 padding from intermediate segment data portions, since the
        decoder merges all data and base64-decodes the combined result.
        Adding padding to individual segments corrupts the merged decode.
        """
        import re
        cleaned = []
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            # Parse the segment to extract header + data
            match = re.match(r'^(IMG\d+x\d+:[TRXtrx]\d+:\d+(?:/\d+)?:)(.+)$', seg)
            if match:
                header = match.group(1)
                data = match.group(2).strip()
                # Remove any trailing = padding from intermediate segment data
                # The decoder will merge all data and handle padding on the combined result
                data = data.rstrip('=')
                cleaned.append(header + data)
            else:
                cleaned.append(seg)
        return cleaned

    @staticmethod
    def _image_to_base64(image: Image.Image) -> str:
        """Convert a PIL Image to base64-encoded PNG string."""
        image_buffer = io.BytesIO()
        image.save(image_buffer, format='PNG')
        return base64.b64encode(image_buffer.getvalue()).decode('ascii')

    @staticmethod
    def _build_success_result(image_data: str, stats: Dict, segment_count: int) -> Dict[str, Any]:
        """Build a standardized success result dictionary."""
        return {
            'success': True,
            'image_data': image_data,
            'stats': {
                'width': stats.get('width', 0),
                'height': stats.get('height', 0),
                'segments_received': segment_count,
                'compression_method': stats.get('compression_method', 'unknown'),
                'bit_depth': stats.get('bit_depth', 0),
                'total_segments': stats.get('total_segments', segment_count)
            },
            'error': None
        }

    @staticmethod
    def _build_error_result(error_msg: str) -> Dict[str, Any]:
        """Build a standardized error result dictionary."""
        return {
            'success': False,
            'image_data': None,
            'stats': {},
            'error': error_msg
        }

    def _fallback_merged_decode(self, cleaned_segments: List[str], segment_count: int) -> Optional[Dict[str, Any]]:
        """
        Fallback decode: manually merge segment data and add correct base64 padding.
        
        Used when the standard decode fails due to base64 padding issues, which
        can occur if segments were corrupted or had padding incorrectly added
        during Meshtastic radio transit.
        
        Args:
            cleaned_segments: Pre-cleaned segment strings
            segment_count: Original segment count for stats
            
        Returns:
            Success result dict if decode succeeded, None if fallback also failed
        """
        import re
        all_data = []
        header_info = None
        
        for seg in cleaned_segments:
            match = re.match(r'^IMG(\d+)x(\d+):([TRXtrx])(\d+):(\d+)(?:/(\d+))?:(.+)$', seg.strip())
            if match:
                if header_info is None:
                    header_info = {
                        'width': int(match.group(1)),
                        'height': int(match.group(2)),
                        'method_code': match.group(3),
                        'bit_depth': int(match.group(4)),
                    }
                all_data.append((int(match.group(5)), match.group(7)))
        
        if not all_data or not header_info:
            return None
        
        all_data.sort(key=lambda x: x[0])
        merged = ''.join(d for _, d in all_data)
        
        # Add base64 padding to the merged data
        padding_needed = (-len(merged)) % 4
        if padding_needed:
            merged += '=' * padding_needed
        
        # Reconstruct as single segment for decoder
        mc = header_info['method_code']
        bd = header_info['bit_depth']
        w = header_info['width']
        h = header_info['height']
        single_segment = f"IMG{w}x{h}:{mc}{bd}:0:{merged}"
        
        logger.info(f"Retrying decode with manually merged data (len={len(merged)}, padded={padding_needed})")
        result = decode_segments_with_stats([single_segment])
        
        if result['success'] and result['image']:
            image_data = self._image_to_base64(result['image'])
            return self._build_success_result(image_data, result['stats'], segment_count)
        
        return None

    def decode_segments(self, segments: List[str]) -> Dict[str, Any]:
        """
        Decode message segments back into an image.
        
        Attempts standard decode first, then falls back to manual merge
        with padding correction if a base64 error occurs.
        
        Args:
            segments: List of Meshtastic message segments
            
        Returns:
            Dictionary with success, image_data, stats, and error fields
            
        Raises:
            DecodingError: If decoder is not available
        """
        if not self.available:
            raise DecodingError("Image decoder not available")
            
        try:
            cleaned_segments = self._clean_segments(segments)
            result = decode_segments_with_stats(cleaned_segments)
            
            if result['success'] and result['image']:
                image_data = self._image_to_base64(result['image'])
                return self._build_success_result(image_data, result['stats'], len(segments))
            
            error_msg = result.get('error', 'Unknown decoding error')
            
            # Try fallback for base64/padding errors
            if 'base64' in str(error_msg).lower() or 'padding' in str(error_msg).lower():
                logger.warning(f"Base64 decode failed, attempting fallback: {error_msg}")
                fallback_result = self._fallback_merged_decode(cleaned_segments, len(segments))
                if fallback_result:
                    return fallback_result
            
            return self._build_error_result(error_msg)
                
        except (ValueError, TypeError, KeyError, IndexError, IOError) as e:
            logger.error(f"Image decoding failed: {e}")
            return self._build_error_result(f"Failed to decode image: {e}")
    
    def decode_segments_simple(self, segments: List[str]) -> Optional[Image.Image]:
        """
        Simple decode that returns PIL Image directly.
        
        Args:
            segments: List of message segments
            
        Returns:
            PIL Image object or None if decoding failed
        """
        if not self.available:
            logger.warning("Image decoder not available")
            return None
            
        try:
            return decode_segments_simple(segments)
        except (ValueError, TypeError, KeyError, IndexError, IOError) as e:
            logger.error(f"Simple decoding failed: {e}")
            return None
    
    def analyze_segments(self, segments: List[str]) -> Dict[str, Any]:
        """
        Analyze message segments without fully decoding.
        
        Args:
            segments: List of message segments
            
        Returns:
            Dictionary with segment analysis information
        """
        if not segments:
            return {
                'valid': False,
                'error': 'No segments provided'
            }
        
        try:
            # Parse the first segment to get basic info
            first_segment = segments[0]
            
            # Expected format: IMG{width}x{height}:{method_code}{bit_depth}:{segment_index}/{total_segments}:{base64_data}
            if not first_segment.startswith('IMG'):
                return {
                    'valid': False,
                    'error': 'Invalid segment format - does not start with IMG'
                }
            
            # Parse header
            header_part = first_segment.split(':')[0]  # IMG{width}x{height}
            dimensions_str = header_part[3:]  # Remove 'IMG' prefix
            
            if 'x' not in dimensions_str:
                return {
                    'valid': False,
                    'error': 'Invalid dimension format'
                }
            
            width_str, height_str = dimensions_str.split('x')
            width = int(width_str)
            height = int(height_str)
            
            # Parse method and bit depth
            method_part = first_segment.split(':')[1]  # {method_code}{bit_depth}
            method_code = method_part[0].upper()
            bit_depth = int(method_part[1])
            
            # Parse segment info
            segment_part = first_segment.split(':')[2]  # {segment_index}/{total_segments}
            segment_index, total_segments = map(int, segment_part.split('/'))
            
            # Method mapping
            method_names = {
                'T': 'tile_rle',
                'R': 'rle_nibble',
                'X': 'rle_nibble_xor'
            }
            
            # Check if we have all segments
            segment_indices = set()
            for segment in segments:
                try:
                    seg_part = segment.split(':')[2]
                    seg_idx = int(seg_part.split('/')[0])
                    segment_indices.add(seg_idx)
                except (IndexError, ValueError):
                    continue
            
            missing_segments = []
            for i in range(total_segments):
                if i not in segment_indices:
                    missing_segments.append(i)
            
            return {
                'valid': True,
                'width': width,
                'height': height,
                'bit_depth': bit_depth,
                'compression_method': method_names.get(method_code, 'unknown'),
                'total_segments': total_segments,
                'received_segments': len(segments),
                'missing_segments': missing_segments,
                'complete': len(missing_segments) == 0,
                'estimated_size': width * height * bit_depth // 8,
                'error': None
            }
            
        except (ValueError, TypeError, IndexError, KeyError) as e:
            logger.error(f"Segment analysis failed: {e}")
            return {
                'valid': False,
                'error': f"Failed to analyze segments: {e}"
            }
    
    def is_image_message(self, message: str) -> bool:
        """
        Check if a message is an image segment.
        
        Args:
            message: Message string to check
            
        Returns:
            True if message appears to be an image segment
        """
        return message.strip().startswith('IMG') and ':' in message

# Global decoder instance
decoder_adapter = DecoderAdapter()