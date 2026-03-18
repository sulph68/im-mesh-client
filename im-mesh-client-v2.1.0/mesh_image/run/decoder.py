"""
Meshtastic Image Decoder
Decodes Meshtastic text messages back to 128x64 images.
"""

import base64
import re
from PIL import Image
from typing import List, Tuple, Dict, Any, Optional
from .tiles import deserialize_tiles, rebuild_tiles, decompress_tile_palette
from .rle import rle_decode
from .rle_nibble import parse_rle_nibble_packet


# ============================================================================
# LIBRARY API - Simple functions for external library usage
# ============================================================================

def decode_segments_simple(segments: List[str]) -> Optional[Image.Image]:
    """
    Simple library API to decode Meshtastic message segments to a PIL Image.
    
    Args:
        segments: List of Meshtastic message segments
        
    Returns:
        PIL Image object or None if decoding failed
        
    Example:
        >>> from run.decoder import decode_segments_simple
        >>> segments = ['IMG64x64:r1:0/2:abc...', 'IMG64x64:r1:1/2:def...']
        >>> image = decode_segments_simple(segments)
        >>> if image:
        ...     image.show()
    """
    image, _ = decode_messages(segments)
    return image


def decode_segments_with_stats(segments: List[str]) -> Dict[str, Any]:
    """
    Library API to decode segments and return both image and detailed statistics.
    
    Args:
        segments: List of Meshtastic message segments
        
    Returns:
        Dictionary containing:
        - image: PIL Image object (None if failed)
        - success: Boolean indicating success
        - stats: Detailed decode statistics
        - error: Error message if failed
        
    Example:
        >>> from run.decoder import decode_segments_with_stats
        >>> result = decode_segments_with_stats(segments)
        >>> if result['success']:
        ...     print(f"Decoded {result['stats']['width']}x{result['stats']['height']} image")
        ...     result['image'].show()
    """
    image, stats = decode_messages(segments)
    
    return {
        'image': image,
        'success': image is not None,
        'stats': stats,
        'error': stats.get('error') if image is None else None
    }


# ============================================================================
# CORE DECODING FUNCTIONS
# ============================================================================


def parse_message(message: str) -> Dict[str, Any]:
    """
    Parse a Meshtastic image message with support for heatshrink compression.
    
    Args:
        message: Message string in format IMG{width}x{height}:{method_code}{mode}:segment:data
        
    Returns:
        Dictionary with parsed components:
        - width: Image width
        - height: Image height  
        - mode: Bit depth (1, 2, or 4)
        - compression_method: Compression method used
        - use_heatshrink: Whether heatshrink compression is used
        - segment: Current segment number
        - total_segments: Total segments (None if single segment)
        - data: Base64 data payload
        - valid: Whether message format is valid
    """
    # Try new format with compression method: IMG{width}x{height}:{method_code}{mode}:segment:data
    pattern_new = r'^IMG(\d+)x(\d+):([TRXtrx])(\d+):(\d+)(?:/(\d+))?:(.+)$'
    match = re.match(pattern_new, message.strip())
    
    if match:
        width = int(match.group(1))
        height = int(match.group(2))
        method_code = match.group(3)
        mode = int(match.group(4))
        segment = int(match.group(5))
        total_segments = int(match.group(6)) if match.group(6) else None
        data = match.group(7)
        
        # Determine if heatshrink compression is used (lowercase method code)
        use_heatshrink = method_code.islower()
        method_code_upper = method_code.upper()
        
        # Map method codes back to names
        method_map = {
            'T': 'tile_rle',
            'R': 'rle_nibble',
            'X': 'rle_nibble_xor'
        }
        compression_method = method_map.get(method_code_upper, 'tile_rle')
        
        # Validate mode
        if mode not in [1, 2, 4]:
            return {
                'valid': False,
                'error': f'Invalid bit depth mode: {mode}. Must be 1, 2, or 4'
            }
        
        # Validate dimensions
        supported_sizes = {(128, 64), (96, 48), (64, 64), (64, 32), (48, 48), (32, 32)}
        if (width, height) not in supported_sizes:
            return {
                'valid': False,
                'error': f'Unsupported image size: {width}x{height}. Supported: {list(supported_sizes)}'
            }
        
        return {
            'valid': True,
            'width': width,
            'height': height,
            'mode': mode,
            'compression_method': compression_method,
            'use_heatshrink': use_heatshrink,
            'segment': segment,
            'total_segments': total_segments,
            'data': data
        }
    
    # Try legacy format: IMG{width}x{height}:mode:segment:data (assume tile_rle)
    pattern_legacy = r'^IMG(\d+)x(\d+):(\d+):(\d+)(?:/(\d+))?:(.+)$'
    match = re.match(pattern_legacy, message.strip())
    
    if match:
        width = int(match.group(1))
        height = int(match.group(2))
        mode = int(match.group(3))
        segment = int(match.group(4))
        total_segments = int(match.group(5)) if match.group(5) else None
        data = match.group(6)
        
        # Validate mode
        if mode not in [1, 2, 4]:
            return {
                'valid': False,
                'error': f'Invalid bit depth mode: {mode}. Must be 1, 2, or 4'
            }
        
        # Validate dimensions
        supported_sizes = {(128, 64), (96, 48), (64, 64), (64, 32), (48, 48), (32, 32)}
        if (width, height) not in supported_sizes:
            return {
                'valid': False,
                'error': f'Unsupported image size: {width}x{height}. Supported: {list(supported_sizes)}'
            }
        
        return {
            'valid': True,
            'width': width,
            'height': height,
            'mode': mode,
            'compression_method': 'tile_rle',  # Legacy format assumes tile_rle
            'use_heatshrink': False,  # Legacy format doesn't use heatshrink
            'segment': segment,
            'total_segments': total_segments,
            'data': data
        }
    
    # Try very old legacy format: IMG128:mode:segment:data
    pattern_old_legacy = r'^IMG128:(\d+):(\d+)(?:/(\d+))?:(.+)$'
    match = re.match(pattern_old_legacy, message.strip())
    
    if match:
        mode = int(match.group(1))
        segment = int(match.group(2))
        total_segments = int(match.group(3)) if match.group(3) else None
        data = match.group(4)
        
        # Validate mode
        if mode not in [1, 2, 4]:
            return {
                'valid': False,
                'error': f'Invalid bit depth mode: {mode}. Must be 1, 2, or 4'
            }
        
        return {
            'valid': True,
            'width': 128,  # Default legacy size
            'height': 64,
            'mode': mode,
            'compression_method': 'tile_rle',  # Legacy format assumes tile_rle
            'use_heatshrink': False,  # Legacy format doesn't use heatshrink
            'segment': segment,
            'total_segments': total_segments,
            'data': data
        }
    
    return {
        'valid': False,
        'error': 'Invalid message format. Expected: IMG{width}x{height}:mode:segment:data or IMG128:mode:segment:data'
    }


def merge_segments(messages: List[str]) -> Dict[str, Any]:
    """
    Merge multiple message segments into complete data.
    
    Args:
        messages: List of message strings
        
    Returns:
        Dictionary with merged data or error info
    """
    if not messages:
        return {'valid': False, 'error': 'No messages provided'}
    
    # Parse all messages
    parsed_messages = []
    for msg in messages:
        parsed = parse_message(msg)
        if not parsed['valid']:
            return parsed
        parsed_messages.append(parsed)
    
    # Check if single message
    if len(parsed_messages) == 1 and parsed_messages[0]['total_segments'] is None:
        return {
            'valid': True,
            'width': parsed_messages[0]['width'],
            'height': parsed_messages[0]['height'],
            'mode': parsed_messages[0]['mode'],
            'compression_method': parsed_messages[0].get('compression_method', 'tile_rle'),
            'use_heatshrink': parsed_messages[0].get('use_heatshrink', False),
            'data': parsed_messages[0]['data']
        }
    
    # Multiple segments - validate and sort
    width = parsed_messages[0]['width']
    height = parsed_messages[0]['height']
    mode = parsed_messages[0]['mode']
    compression_method = parsed_messages[0].get('compression_method', 'tile_rle')
    use_heatshrink = parsed_messages[0].get('use_heatshrink', False)
    total_segments = parsed_messages[0]['total_segments']
    
    if total_segments is None:
        return {
            'valid': False,
            'error': 'Mixed single and multi-segment messages'
        }
    
    # Validate all segments have same dimensions, mode and total
    for parsed in parsed_messages:
        if parsed['width'] != width or parsed['height'] != height:
            return {
                'valid': False,
                'error': f'Inconsistent image dimensions: {width}x{height} vs {parsed["width"]}x{parsed["height"]}'
            }
        if parsed['mode'] != mode:
            return {
                'valid': False,
                'error': f'Inconsistent bit depth modes: {mode} vs {parsed["mode"]}'
            }
        if parsed['total_segments'] != total_segments:
            return {
                'valid': False,
                'error': f'Inconsistent total segment counts: {total_segments} vs {parsed["total_segments"]}'
            }
        # Validate compression method consistency
        if parsed.get('compression_method', 'tile_rle') != compression_method:
            return {
                'valid': False,
                'error': f'Inconsistent compression methods: {compression_method} vs {parsed.get("compression_method", "tile_rle")}'
            }
        # Validate heatshrink consistency
        if parsed.get('use_heatshrink', False) != use_heatshrink:
            return {
                'valid': False,
                'error': f'Inconsistent heatshrink usage: {use_heatshrink} vs {parsed.get("use_heatshrink", False)}'
            }
    
    # Sort by segment number
    parsed_messages.sort(key=lambda x: x['segment'])
    
    # Check for missing segments
    expected_segments = set(range(total_segments))
    actual_segments = set(p['segment'] for p in parsed_messages)
    
    if actual_segments != expected_segments:
        missing = expected_segments - actual_segments
        return {
            'valid': False,
            'error': f'Missing segments: {sorted(missing)}'
        }
    
    # Merge data
    merged_data = ''.join(p['data'] for p in parsed_messages)
    
    return {
        'valid': True,
        'width': width,
        'height': height,
        'mode': mode,
        'compression_method': compression_method,
        'use_heatshrink': use_heatshrink,
        'data': merged_data,
        'total_segments': total_segments
    }


def base64_decode(data: str) -> bytes:
    """
    Decode base64 data with error handling.
    
    Args:
        data: Base64 encoded string
        
    Returns:
        Decoded bytes
    """
    try:
        return base64.b64decode(data)
    except Exception as e:
        raise ValueError(f"Invalid base64 data: {e}")


def decompress_tile_bytes(tile_bytes: bytes, mode: int, tile_size: int) -> List[int]:
    """
    Decompress tile bytes back to pixel values with robust error handling.
    
    Args:
        tile_bytes: Compressed tile data
        mode: Bit depth mode (1, 2, or 4)
        tile_size: Size of tile (4, 8, etc.)
        
    Returns:
        List of pixel values for the tile
    """
    pixels = []
    pixels_per_tile = tile_size * tile_size
    
    try:
        if not tile_bytes:
            # Empty tile - return all zeros
            return [0] * pixels_per_tile
        
        # Check if this is palette compressed (first byte is palette size <= 4)
        if len(tile_bytes) > 0 and tile_bytes[0] <= 4:
            # Likely palette compressed
            palette_size = tile_bytes[0]
            if palette_size == 0:
                return [0] * pixels_per_tile
            
            if len(tile_bytes) < 1 + palette_size:
                # Invalid palette data, fallback to raw decompression
                return decompress_raw_tile(tile_bytes, mode, pixels_per_tile)
            
            palette = list(tile_bytes[1:1 + palette_size])
            packed_data = tile_bytes[1 + palette_size:]
            
            # Determine bits per pixel based on palette size
            if palette_size == 1:
                pixels = [palette[0]] * pixels_per_tile
            elif palette_size == 2:
                pixels = decompress_palette_1bit(packed_data, palette, pixels_per_tile)
            elif palette_size <= 4:
                pixels = decompress_palette_2bit(packed_data, palette, pixels_per_tile)
            else:
                # Fallback to raw
                pixels = decompress_raw_tile(tile_bytes, mode, pixels_per_tile)
        else:
            # Raw compressed tile
            pixels = decompress_raw_tile(tile_bytes, mode, pixels_per_tile)
        
        # Ensure correct length
        while len(pixels) < pixels_per_tile:
            pixels.append(0)
        
        return pixels[:pixels_per_tile]
        
    except Exception:
        # On any error, return black tile of correct size
        return [0] * pixels_per_tile


def decompress_raw_tile(tile_bytes: bytes, mode: int, pixels_per_tile: int) -> List[int]:
    """Decompress raw tile data."""
    pixels = []
    
    if mode == 1:
        # 1-bit: 8 pixels per byte
        for byte_val in tile_bytes:
            for bit in range(8):
                if len(pixels) < pixels_per_tile:
                    pixels.append((byte_val >> (7 - bit)) & 1)
    elif mode == 2:
        # 2-bit: 4 pixels per byte
        for byte_val in tile_bytes:
            for shift in [6, 4, 2, 0]:
                if len(pixels) < pixels_per_tile:
                    pixels.append((byte_val >> shift) & 3)
    elif mode == 4:
        # 4-bit: 2 pixels per byte
        for byte_val in tile_bytes:
            if len(pixels) < pixels_per_tile:
                pixels.append((byte_val >> 4) & 0xF)
            if len(pixels) < pixels_per_tile:
                pixels.append(byte_val & 0xF)
    
    return pixels


def decompress_palette_1bit(packed_data: bytes, palette: List[int], pixels_per_tile: int) -> List[int]:
    """Decompress 1-bit palette compressed data."""
    pixels = []
    for byte_val in packed_data:
        for bit in range(8):
            if len(pixels) < pixels_per_tile:
                index = (byte_val >> (7 - bit)) & 1
                if index < len(palette):
                    pixels.append(palette[index])
                else:
                    pixels.append(0)
    return pixels


def decompress_palette_2bit(packed_data: bytes, palette: List[int], pixels_per_tile: int) -> List[int]:
    """Decompress 2-bit palette compressed data."""
    pixels = []
    for byte_val in packed_data:
        for shift in [6, 4, 2, 0]:
            if len(pixels) < pixels_per_tile:
                index = (byte_val >> shift) & 3
                if index < len(palette):
                    pixels.append(palette[index])
                else:
                    pixels.append(0)
    return pixels


def rebuild_image(tiles: List[List[int]], width: int = 128, height: int = 64, bit_depth: int = 1, tile_size: int = 8) -> Image.Image:
    """
    Rebuild image from tile data.
    
    Args:
        tiles: List of tile pixel data
        width: Image width
        height: Image height
        bit_depth: Bit depth for pixel scaling
        tile_size: Size of each tile (8, 4, or 2)
        
    Returns:
        PIL Image
    """
    tiles_x = width // tile_size
    tiles_y = height // tile_size
    expected_tiles = tiles_x * tiles_y
    
    if len(tiles) != expected_tiles:
        raise ValueError(f"Expected {expected_tiles} tiles for {width}x{height} with {tile_size}x{tile_size} tiles, got {len(tiles)}")
    
    pixels = []
    
    # Rebuild pixel array from tiles
    for y in range(height):
        for x in range(width):
            tile_x = x // tile_size
            tile_y = y // tile_size
            tile_index = tile_y * tiles_x + tile_x
            
            pixel_x = x % tile_size
            pixel_y = y % tile_size
            pixel_index = pixel_y * tile_size + pixel_x
            
            if tile_index < len(tiles) and pixel_index < len(tiles[tile_index]):
                pixel_value = tiles[tile_index][pixel_index]
            else:
                pixel_value = 0  # Fallback
            pixels.append(pixel_value)
    
    return pixels_to_image(pixels, width, height, bit_depth)


def pixels_to_image(pixels: List[int], width: int, height: int, bit_depth: int = 1) -> Image.Image:
    """
    Convert pixel array to PIL Image.
    
    Args:
        pixels: Flat pixel array with values 0 to (2^bit_depth - 1)
        width: Image width
        height: Image height
        bit_depth: Bit depth for scaling
        
    Returns:
        PIL Image in grayscale
    """
    if bit_depth == 1:
        max_val = 1
    elif bit_depth == 2:
        max_val = 3
    elif bit_depth == 4:
        max_val = 15
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")
    
    # Scale pixel values to 0-255
    scaled_pixels = []
    for pixel in pixels:
        scaled_pixel = round(pixel * 255.0 / max_val)
        scaled_pixels.append(scaled_pixel)
    
    # Create PIL image
    image = Image.new('L', (width, height))
    image.putdata(scaled_pixels)
    
    return image


def decode_messages(messages: List[str]) -> Tuple[Optional[Image.Image], Dict[str, Any]]:
    """
    Complete decoding pipeline from messages to image.
    
    Args:
        messages: List of Meshtastic message strings
        
    Returns:
        Tuple of (decoded_image, decode_stats)
        decoded_image is None if decoding failed
    """
    try:
        # Step 1: Merge segments
        merged = merge_segments(messages)
        if not merged['valid']:
            return None, {'success': False, 'error': merged['error']}
        
        # Extract image info
        width = merged.get('width', 128)
        height = merged.get('height', 64)
        mode = merged['mode']
        compression_method = merged.get('compression_method', 'tile_rle')
        use_heatshrink = merged.get('use_heatshrink', False)
        base64_data = merged['data']
        
        # Step 2: Decode base64
        try:
            compressed_bytes = base64_decode(base64_data)
        except ValueError as e:
            return None, {'success': False, 'error': str(e)}
        
        # Step 3: Decompress heatshrink if used
        if use_heatshrink:
            try:
                import heatshrink2
                compressed_bytes = heatshrink2.decompress(compressed_bytes)
            except Exception as e:
                return None, {'success': False, 'error': f'Heatshrink decompression failed: {str(e)}'}
        
        # Decode based on compression method
        if compression_method == 'tile_rle':
            image, stats = _decode_tile_rle(compressed_bytes, width, height, mode)
        elif compression_method in ['rle_nibble', 'rle_nibble_xor']:
            image, stats = _decode_rle_nibble(compressed_bytes, width, height, mode, compression_method)
        else:
            return None, {'success': False, 'error': f'Unknown compression method: {compression_method}'}
        
        # Update stats with segment info
        stats['total_segments'] = merged.get('total_segments', 1)
        stats['base64_length'] = len(base64_data)
        stats['use_heatshrink'] = use_heatshrink
        
        return image, stats
        
    except Exception as e:
        import traceback
        return None, {
            'success': False, 
            'error': f'Decoding error: {str(e)}',
            'traceback': traceback.format_exc()
        }
    
    return image, stats


def _decode_tile_rle(compressed_bytes: bytes, width: int, height: int, mode: int) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Decode image using tile_rle compression method (the original algorithm).
    """
    # Step 3: RLE decompress
    serialized_data = rle_decode(compressed_bytes)
    
    # Step 4: Deserialize tiles
    tile_data = deserialize_tiles(serialized_data)
    
    # Determine tile size based on image dimensions
    tile_size = tile_data.get('tile_size', 8 if width >= 64 else 4)
    tiles_x = width // tile_size
    tiles_y = height // tile_size
    total_tiles = tiles_x * tiles_y
    
    # Step 5: Rebuild tiles with better error handling
    rebuilt_tiles = []
    unique_tiles = tile_data['unique_tiles']
    reference_map = tile_data['reference_map']
    
    for i in range(total_tiles):
        unique_index = reference_map.get(i, 0)
        if unique_index < len(unique_tiles):
            tile_bytes = unique_tiles[unique_index]['data']
            # Decompress tile based on expected format
            pixels = decompress_tile_bytes(tile_bytes, mode, tile_size)
            rebuilt_tiles.append(pixels)
        else:
            # Fallback: create black tile
            pixels_per_tile = tile_size * tile_size
            rebuilt_tiles.append([0] * pixels_per_tile)
    
    # Step 6: Rebuild image
    image = rebuild_image(rebuilt_tiles, width, height, mode, tile_size)
    
    # Calculate statistics
    stats = {
        'success': True,
        'width': width,
        'height': height,
        'mode': mode,
        'compressed_bytes': len(compressed_bytes),
        'decoded_bytes': len(serialized_data),
        'total_pixels': width * height,
        'unique_tiles': len(unique_tiles),
        'total_tiles': total_tiles,
        'tile_size': tile_size,
        'compression_method': 'tile_rle'
    }
    
    return image, stats


def _decode_rle_nibble(compressed_bytes: bytes, width: int, height: int, mode: int, compression_method: str = 'rle_nibble') -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Decode image using rle_nibble or rle_nibble_xor compression method.
    """
    # Parse the RLE nibble packet - returns (pixels, width, height, bit_depth, stats)
    pixels, decoded_width, decoded_height, decoded_bit_depth, packet_stats = parse_rle_nibble_packet(compressed_bytes)
    
    # Use the dimensions from the packet if available, otherwise use provided values
    actual_width = decoded_width if decoded_width > 0 else width
    actual_height = decoded_height if decoded_height > 0 else height
    
    # Convert to image based on bit depth
    if mode == 1:
        # For 1-bit mode, pixels should already be 0 or 1, convert to 0 or 255
        image_pixels = [p * 255 for p in pixels]
    elif mode == 2:
        # For 2-bit mode, pixels should be 0-3, convert to 0-255 range
        image_pixels = [p * 85 for p in pixels]  # 255/3 ≈ 85
    elif mode == 4:
        # For 4-bit mode, pixels should be 0-15, convert to 0-255 range
        image_pixels = [p * 17 for p in pixels]  # 255/15 = 17
    else:
        # Default: assume already in 0-255 range
        image_pixels = pixels[:]
    
    # Ensure we have the right number of pixels
    expected_pixels = actual_width * actual_height
    if len(image_pixels) < expected_pixels:
        # Pad with zeros if needed
        image_pixels.extend([0] * (expected_pixels - len(image_pixels)))
    elif len(image_pixels) > expected_pixels:
        # Trim if too many
        image_pixels = image_pixels[:expected_pixels]
    
    # Create image
    image = Image.new('L', (actual_width, actual_height))
    image.putdata(image_pixels)
    
    # Calculate statistics
    stats = {
        'success': True,
        'width': actual_width,
        'height': actual_height,
        'mode': mode,
        'compressed_bytes': len(compressed_bytes),
        'decoded_pixels': len(pixels),
        'total_pixels': expected_pixels,
        'compression_method': compression_method,
        'packet_stats': packet_stats,
        # Add tile-related stats for UI compatibility (N/A for pixel-stream methods)
        'unique_tiles': 'N/A',
        'total_tiles': 'N/A',
        'tile_size': 'N/A'
    }
    
    return image, stats


def validate_message_format(message: str) -> Dict[str, Any]:
    """
    Validate message format without full decoding.
    
    Args:
        message: Message string to validate
        
    Returns:
        Dictionary with validation results
    """
    parsed = parse_message(message)
    if not parsed['valid']:
        return parsed
    
    # Additional validation
    data = parsed['data']
    
    # Check if base64 data is valid
    try:
        base64.b64decode(data)
        base64_valid = True
    except:
        base64_valid = False
    
    return {
        'valid': True,
        'mode': parsed['mode'],
        'segment': parsed['segment'],
        'total_segments': parsed['total_segments'],
        'data_length': len(data),
        'base64_valid': base64_valid
    }