"""
Meshtastic Image Encoder
Converts images to compressed Meshtastic-compatible text messages.
"""

from PIL import Image
import base64
import math
from typing import List, Tuple, Dict, Any
from .config import MESSAGE_PREFIX
from .models import ImageDimensions, CompressionConfig, SegmentConfig, CompressionStats
from .image_processor import ImageProcessor
from .compression import CompressionFactory


def resize_image(image: Image.Image, width: int = 128, height: int = 64) -> Image.Image:
    """
    Resize image to target dimensions using center crop to maintain quality.
    
    This function:
    1. Calculates the target aspect ratio
    2. Crops the image from the center to match that aspect ratio
    3. Resizes the cropped image to the exact target dimensions
    
    Args:
        image: PIL Image object
        width: Target width
        height: Target height
        
    Returns:
        Resized PIL Image with exact target dimensions
    """
    # Calculate target aspect ratio
    target_ratio = width / height
    current_ratio = image.width / image.height
    
    # Determine crop dimensions
    if current_ratio > target_ratio:
        # Image is wider than target - crop width
        new_width = int(image.height * target_ratio)
        new_height = image.height
        left = (image.width - new_width) // 2
        top = 0
        right = left + new_width
        bottom = image.height
    else:
        # Image is taller than target - crop height  
        new_width = image.width
        new_height = int(image.width / target_ratio)
        left = 0
        top = (image.height - new_height) // 2
        right = image.width
        bottom = top + new_height
    
    # Crop to target aspect ratio
    cropped_image = image.crop((left, top, right, bottom))
    
    # Resize to exact target dimensions
    return cropped_image.resize((width, height), Image.Resampling.LANCZOS)


def quantize_image(image: Image.Image, bit_depth: int) -> Image.Image:
    """
    Quantize image to specified bit depth.
    
    Args:
        image: PIL Image in grayscale
        bit_depth: 1, 2, or 4 bits
        
    Returns:
        Quantized PIL Image
    """
    # Convert to grayscale first if not already
    if image.mode != 'L':
        image = image.convert('L')
    
    # Determine number of levels
    if bit_depth == 1:
        levels = 2
    elif bit_depth == 2:
        levels = 4
    elif bit_depth == 4:
        levels = 16
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")
    
    # Quantize to specified levels
    # Scale down then back up to reduce levels
    pixels = list(image.getdata())
    max_val = levels - 1
    
    quantized_pixels = []
    for pixel in pixels:
        # Map 0-255 to 0-(levels-1)
        level = round(pixel * max_val / 255.0)
        # Map back to 0-255 for display
        quantized_pixel = round(level * 255.0 / max_val)
        quantized_pixels.append(quantized_pixel)
    
    # Create new image with quantized data
    quantized_image = Image.new('L', image.size)
    quantized_image.putdata(quantized_pixels)
    
    return quantized_image


def image_to_pixels(image: Image.Image, bit_depth: int) -> List[int]:
    """
    Convert image to flat pixel array with proper bit depth values.
    
    Args:
        image: PIL Image
        bit_depth: Target bit depth (1, 2, or 4)
        
    Returns:
        Flat list of pixel values in range 0 to (2^bit_depth - 1)
    """
    if bit_depth == 1:
        max_val = 1
    elif bit_depth == 2:
        max_val = 3
    elif bit_depth == 4:
        max_val = 15
    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")
    
    pixels = list(image.getdata())
    # Convert from 0-255 to 0-max_val
    converted_pixels = []
    for pixel in pixels:
        level = round(pixel * max_val / 255.0)
        converted_pixels.append(level)
    
    return converted_pixels


def encode_image_with_config(image: Image.Image, config: CompressionConfig, 
                           dimensions: ImageDimensions, segment_config: SegmentConfig = None) -> Tuple[List[str], CompressionStats]:
    """
    Modern encode function using configuration objects.
    
    Args:
        image: PIL Image to encode
        config: Compression configuration
        dimensions: Target dimensions
        segment_config: Segment configuration
        
    Returns:
        Tuple of (message_segments, compression_stats)
    """
    if segment_config is None:
        segment_config = SegmentConfig()
    
    # Preprocess image for compression strategies
    processed_image = _preprocess_image_for_compression(image, config, dimensions)
    
    # Get compression strategy
    strategy = CompressionFactory.get_strategy(config.method)
    
    # Compress image
    compressed_data, stats = strategy.compress(processed_image, config)
    
    # Apply heatshrink compression if enabled
    if config.use_heatshrink:
        try:
            import heatshrink2
            compressed_data = heatshrink2.compress(compressed_data, window_sz2=11, lookahead_sz2=4)
        except ImportError:
            # Heatshrink not available, continue without it
            pass
    
    # Convert to base64
    base64_data = base64.b64encode(compressed_data).decode('ascii')
    stats.base64_encoded_chars = len(base64_data)
    
    # Create message segments
    segments = _create_message_segments(
        base64_data, 
        dimensions, 
        config, 
        segment_config.max_length
    )
    
    return segments, stats


def _preprocess_image_for_compression(image: Image.Image, config: CompressionConfig, dimensions: ImageDimensions) -> Image.Image:
    """
    Preprocess image for compression strategies.
    
    Args:
        image: Original PIL Image
        config: Compression configuration
        dimensions: Target dimensions
        
    Returns:
        Processed PIL Image ready for compression
    """
    from .image_processor import ImageProcessor
    
    # Normalize image
    normalized = ImageProcessor.normalize_image(image)
    
    # Resize to target dimensions
    resized = ImageProcessor.resize_with_aspect_ratio(normalized, dimensions)
    
    # Convert to grayscale and quantize
    grayscale = resized.convert('L')
    quantized = ImageProcessor.quantize_image(grayscale, config)
    
    return quantized


def encode_image(image: Image.Image, bit_depth: int, target_width: int = 128, target_height: int = 64, 
                compression_method: str = 'tile_rle', max_segment_length: int = 220) -> Tuple[List[str], Dict[str, Any]]:
    """
    Legacy encode function for backward compatibility.
    
    Args:
        image: PIL Image to encode
        bit_depth: Bit depth (1, 2, or 4)
        target_width: Target image width
        target_height: Target image height
        compression_method: Compression method
        max_segment_length: Maximum length per message segment
        
    Returns:
        Tuple of (message_segments, compression_stats_dict)
    """
    # Create configuration objects
    config = CompressionConfig(method=compression_method, bit_depth=bit_depth)
    dimensions = ImageDimensions(target_width, target_height)
    segment_config = SegmentConfig(max_segment_length)
    
    # Use modern implementation
    segments, stats = encode_image_with_config(image, config, dimensions, segment_config)
    
    # Convert stats back to dictionary for backward compatibility
    stats_dict = {
        'compression_method': stats.compression_method,
        'compression_ratio': stats.compression_ratio,
        'unique_tiles': stats.unique_tiles if stats.unique_tiles is not None else 'N/A',
        'total_tiles': stats.total_tiles if stats.total_tiles is not None else 'N/A',
        'base64_encoded_chars': stats.base64_encoded_chars
    }
    
    return segments, stats_dict


def _encode_with_tile_rle(pixels: List[int], bit_depth: int, target_width: int, target_height: int, max_segment_length: int = 220) -> Tuple[List[str], Dict[str, Any]]:
    """
    Encode using the original tile palette + RLE compression method.
    """
    # Step 2: Split into tiles (adaptive tile size based on image dimensions)
    tile_size = 8 if target_width >= 64 else 4  # Use 8x8 for larger images, 4x4 for smaller
    tiles_x = target_width // tile_size
    tiles_y = target_height // tile_size
    total_tiles = tiles_x * tiles_y
    
    # Split pixels into tiles
    tiles = []
    for tile_y in range(tiles_y):
        for tile_x in range(tiles_x):
            tile = []
            for y in range(tile_size):
                for x in range(tile_size):
                    pixel_x = tile_x * tile_size + x
                    pixel_y = tile_y * tile_size + y
                    pixel_index = pixel_y * target_width + pixel_x
                    if pixel_index < len(pixels):
                        tile.append(pixels[pixel_index])
                    else:
                        tile.append(0)  # Padding
            tiles.append(tile)
    
    # Step 3: Compress tiles with palette compression
    compressed_tiles = []
    for tile in tiles:
        compressed_tile = compress_tile_palette(tile)
        compressed_tiles.append(compressed_tile)
    
    # Step 4: Deduplicate tiles
    unique_tiles, reference_map = deduplicate_tiles([tile['data'] for tile in compressed_tiles])
    
    # Create proper tile data structure
    tile_data = {
        'unique_tiles': [{'data': tile} for tile in unique_tiles],
        'reference_map': reference_map,
        'total_tiles': total_tiles,
        'tile_size': tile_size,
        'tiles_x': tiles_x,
        'tiles_y': tiles_y
    }
    
    # Step 5: Serialize tiles
    serialized_data = serialize_tiles(tile_data)
    
    # Step 6: Apply RLE compression
    rle_compressed = rle_encode(serialized_data)
    
    # Step 7: Base64 encode
    base64_data = base64.b64encode(rle_compressed).decode('ascii')
    
    # Step 8: Create message segments with size information
    segments = encode_message(base64_data, bit_depth, target_width, target_height, max_length=max_segment_length, compression_method='tile_rle', use_heatshrink=True)
    
    # Calculate compression statistics
    stats = {
        'compression_method': 'tile_rle',
        'image_width': target_width,
        'image_height': target_height,
        'original_pixels': target_width * target_height,
        'total_tiles': total_tiles,
        'unique_tiles': len(unique_tiles),
        'deduplication_ratio': len(unique_tiles) / total_tiles if total_tiles > 0 else 0,
        'serialized_bytes': len(serialized_data),
        'rle_compressed_bytes': len(rle_compressed),
        'base64_encoded_chars': len(base64_data),
        'compression_ratio': len(rle_compressed) / len(pixels) if len(pixels) > 0 else 0,
        'total_segments': len(segments),
        'estimated_original_bytes': (target_width * target_height * bit_depth) / 8.0,
        'tile_size': tile_size
    }
    
    return segments, stats


def _encode_with_rle_nibble(pixels: List[int], bit_depth: int, target_width: int, target_height: int, 
                          use_row_xor: bool = False, max_segment_length: int = 220) -> Tuple[List[str], Dict[str, Any]]:
    """
    Encode using RLE with nibble packing compression method.
    """
    # Create RLE nibble packet
    packet = create_rle_nibble_packet(pixels, target_width, target_height, bit_depth, use_row_xor)
    
    # Base64 encode
    base64_data = base64.b64encode(packet).decode('ascii')
    
    # Create message segments
    method_name = 'rle_nibble_xor' if use_row_xor else 'rle_nibble'
    segments = encode_message(base64_data, bit_depth, target_width, target_height, max_length=max_segment_length, compression_method=method_name, use_heatshrink=True)
    
    # Calculate compression statistics
    stats = {
        'compression_method': method_name,
        'image_width': target_width,
        'image_height': target_height,
        'original_pixels': target_width * target_height,
        'use_row_xor': use_row_xor,
        'packet_size': len(packet),
        'header_size': 8,
        'compressed_data_size': len(packet) - 8,
        'base64_encoded_chars': len(base64_data),
        'compression_ratio': len(packet) / len(pixels) if len(pixels) > 0 else 0,
        'total_segments': len(segments),
        'estimated_original_bytes': (target_width * target_height * bit_depth) / 8.0,
        'rle_analysis': analyze_rle_nibble_patterns(pixels),
        # Add tile-related stats for UI compatibility (N/A for pixel-stream methods)
        'unique_tiles': 'N/A',
        'total_tiles': 'N/A',
        'tile_size': 'N/A'
    }
    
    return segments, stats


def encode_message(base64_data: str, mode: int, width: int = 128, height: int = 64, 
                  max_length: int = 200, compression_method: str = 'tile_rle', 
                  use_heatshrink: bool = True) -> List[str]:
    """
    Split base64 data into Meshtastic message segments with optional heatshrink compression.
    
    Args:
        base64_data: Base64-encoded compressed data
        mode: Bit depth mode (1, 2, or 4)
        width: Image width
        height: Image height
        max_length: Maximum characters per message (default 200)
        compression_method: Compression method used
        use_heatshrink: Whether to apply heatshrink compression to the base64 data
        
    Returns:
        List of message segments
    """
    import heatshrink2
    import base64
    
    # Apply heatshrink compression if requested
    if use_heatshrink:
        # Convert base64 to bytes, compress with heatshrink, then back to base64
        original_bytes = base64.b64decode(base64_data.encode('ascii'))
        heatshrink_compressed = heatshrink2.compress(original_bytes)
        base64_data = base64.b64encode(heatshrink_compressed).decode('ascii')
    
    # Map compression methods to shorter codes for message format
    method_codes = {
        'tile_rle': 'T',
        'rle_nibble': 'R',
        'rle_nibble_xor': 'X'
    }
    method_code = method_codes.get(compression_method, 'T')
    
    # Add heatshrink flag to method code
    if use_heatshrink:
        method_code = method_code.lower()  # Lowercase indicates heatshrink compression
    
    # Calculate available space for data
    # Format: "IMG{width}x{height}:{method_code}{mode}:S:DATA" or "IMG{width}x{height}:{method_code}{mode}:S/T:DATA"
    prefix_base = f"IMG{width}x{height}:{method_code}{mode}:"
    
    if len(base64_data) <= max_length - len(prefix_base) - 2:  # -2 for segment number
        # Single segment
        return [f"{prefix_base}0:{base64_data}"]
    
    # Multiple segments needed
    segments = []
    segment_prefix_len = len(prefix_base) + 6  # "S/T:" where S and T are single digits
    max_data_per_segment = max_length - segment_prefix_len
    
    total_segments = math.ceil(len(base64_data) / max_data_per_segment)
    
    for i in range(total_segments):
        start_pos = i * max_data_per_segment
        end_pos = min(start_pos + max_data_per_segment, len(base64_data))
        segment_data = base64_data[start_pos:end_pos]
        
        segment_msg = f"{prefix_base}{i}/{total_segments}:{segment_data}"
        segments.append(segment_msg)
    
    return segments


def _create_message_segments(base64_data: str, dimensions: ImageDimensions, 
                           config: CompressionConfig, max_segment_length: int) -> List[str]:
    """Create message segments from base64 data."""
    # Calculate header overhead: IMG{width}x{height}:{method_code}{bit_depth}:{segment}/{total}:
    header_base = f"{MESSAGE_PREFIX}{dimensions.width}x{dimensions.height}:{config.method_code}{config.bit_depth}:"
    segment_suffix = ":"
    
    # Reserve space for segment numbering (estimate "999/999:")
    segment_numbering_space = 8
    
    # Calculate available space for data
    max_data_per_segment = max_segment_length - len(header_base) - len(segment_suffix) - segment_numbering_space
    
    # Split data into segments
    total_segments = math.ceil(len(base64_data) / max_data_per_segment)
    segments = []
    
    for i in range(total_segments):
        start_pos = i * max_data_per_segment
        end_pos = min(start_pos + max_data_per_segment, len(base64_data))
        segment_data = base64_data[start_pos:end_pos]
        
        if total_segments == 1:
            segment_msg = f"{header_base}0:{segment_data}"
        else:
            segment_msg = f"{header_base}{i}/{total_segments}:{segment_data}"
        
        segments.append(segment_msg)
    
    return segments


def prepare_image_for_encoding(image_file, bit_depth: int = 1, target_width: int = 128, target_height: int = 64) -> Tuple[Image.Image, Image.Image, Dict[str, Any]]:
    """
    Legacy function for backward compatibility.
    
    Args:
        image_file: File object or path to image
        bit_depth: Target bit depth
        target_width: Target image width
        target_height: Target image height
        
    Returns:
        Tuple of (original_image, processed_image, preparation_stats_dict)
    """
    # Create configuration objects
    config = CompressionConfig(method='tile_rle', bit_depth=bit_depth)
    dimensions = ImageDimensions(target_width, target_height)
    
    # Use modern implementation
    original, processed, stats = ImageProcessor.prepare_image_for_encoding(image_file, config, dimensions)
    
    # Convert stats to dictionary for backward compatibility
    stats_dict = {
        'original_size': stats.original_size,
        'target_size': stats.target_size,
        'original_mode': stats.original_mode,
        'bit_depth': stats.bit_depth,
        'quantization_levels': stats.quantization_levels
    }
    
    return original, processed, stats_dict


# ============================================================================
# LIBRARY API - Simple functions for external library usage  
# ============================================================================

def encode_image_simple(image: Image.Image, bit_depth: int = 1, width: int = 64, height: int = 64, 
                       compression_method: str = 'rle_nibble', segment_length: int = 220) -> List[str]:
    """
    Simple library API to encode a PIL Image to Meshtastic message segments.
    
    Args:
        image: PIL Image object
        bit_depth: Bit depth (1, 2, or 4)  
        width: Target width
        height: Target height
        compression_method: 'tile_rle', 'rle_nibble', or 'rle_nibble_xor'
        segment_length: Maximum segment length
        
    Returns:
        List of message segments ready for transmission
        
    Example:
        >>> from PIL import Image
        >>> from run.encoder import encode_image_simple
        >>> img = Image.open('test.png')
        >>> segments = encode_image_simple(img, bit_depth=1, width=64, height=64)
        >>> print(f"Created {len(segments)} segments")
    """
    # Use the existing encode_image function which accepts PIL Image directly
    segments, _ = encode_image(image, bit_depth, width, height, compression_method, segment_length)
    return segments


def encode_image_file(image_path: str, bit_depth: int = 1, width: int = 64, height: int = 64,
                     compression_method: str = 'rle_nibble', segment_length: int = 220) -> Dict[str, Any]:
    """
    Simple library API to encode an image file to Meshtastic message segments with stats.
    
    Args:
        image_path: Path to image file
        bit_depth: Bit depth (1, 2, or 4)
        width: Target width  
        height: Target height
        compression_method: 'tile_rle', 'rle_nibble', or 'rle_nibble_xor'
        segment_length: Maximum segment length
        
    Returns:
        Dictionary containing:
        - segments: List of message segments
        - compression_stats: Compression statistics
        - preparation_stats: Image preparation statistics
        
    Example:
        >>> from run.encoder import encode_image_file
        >>> result = encode_image_file('test.png', bit_depth=1, width=64, height=64)
        >>> segments = result['segments']
        >>> print(f"Compression ratio: {result['compression_stats']['compression_ratio']:.2f}")
    """
    with open(image_path, 'rb') as f:
        original_image, processed_image, prep_stats = prepare_image_for_encoding(f, bit_depth, width, height)
    
    segments, compression_stats = encode_image(processed_image, bit_depth, width, height, compression_method, segment_length)
    
    return {
        'segments': segments,
        'compression_stats': compression_stats,
        'preparation_stats': prep_stats,
        'original_image': original_image,
        'processed_image': processed_image
    }


def test_roundtrip_encoding(image: Image.Image, bit_depth: int = 1, target_width: int = 128, target_height: int = 64) -> Dict[str, Any]:
    """
    Test encode/decode roundtrip for a given image.
    
    Args:
        image: PIL Image to test
        bit_depth: Bit depth (1, 2, or 4)
        target_width: Target image width
        target_height: Target image height
        
    Returns:
        Dictionary with test results:
        - success: Whether roundtrip was successful
        - original_segments: Encoded segments
        - decoded_image: Decoded PIL Image (if successful)
        - compression_stats: Compression statistics
        - decode_stats: Decode statistics
        - comparison: Pixel comparison results
        - error: Error message (if failed)
    """
    try:
        from .decoder import decode_messages
        
        # Step 1: Encode the image
        segments, compression_stats = encode_image(image, bit_depth, target_width, target_height)
        
        # Step 2: Decode the segments
        decoded_image, decode_stats = decode_messages(segments)
        
        if decoded_image is None:
            return {
                'success': False,
                'error': f"Decode failed: {decode_stats.get('error', 'Unknown error')}",
                'original_segments': segments,
                'compression_stats': compression_stats,
                'decode_stats': decode_stats
            }
        
        # Step 3: Compare original and decoded images
        # First prepare original image for comparison (quantized version)
        processed_image = resize_image(image, target_width, target_height)
        processed_image = quantize_image(processed_image, bit_depth)
        
        # Compare pixel by pixel
        orig_pixels = list(processed_image.getdata())
        dec_pixels = list(decoded_image.getdata())
        
        if len(orig_pixels) != len(dec_pixels):
            return {
                'success': False,
                'error': f"Pixel count mismatch: {len(orig_pixels)} vs {len(dec_pixels)}",
                'original_segments': segments,
                'decoded_image': decoded_image,
                'compression_stats': compression_stats,
                'decode_stats': decode_stats
            }
        
        # Calculate pixel differences
        differences = []
        exact_matches = 0
        tolerance = get_tolerance_for_bit_depth(bit_depth)
        
        for orig, dec in zip(orig_pixels, dec_pixels):
            diff = abs(orig - dec)
            differences.append(diff)
            if diff <= tolerance:
                exact_matches += 1
        
        total_pixels = len(orig_pixels)
        max_diff = max(differences) if differences else 0
        avg_diff = sum(differences) / total_pixels if total_pixels > 0 else 0
        accuracy = (exact_matches / total_pixels) * 100 if total_pixels > 0 else 0
        
        comparison = {
            'total_pixels': total_pixels,
            'exact_matches': exact_matches,
            'accuracy_percent': accuracy,
            'max_difference': max_diff,
            'avg_difference': avg_diff,
            'tolerance_used': tolerance,
            'is_perfect': max_diff <= tolerance
        }
        
        return {
            'success': True,
            'original_segments': segments,
            'decoded_image': decoded_image,
            'compression_stats': compression_stats,
            'decode_stats': decode_stats,
            'comparison': comparison,
            'is_perfect_roundtrip': comparison['is_perfect']
        }
        
    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': f"Roundtrip test error: {str(e)}",
            'traceback': traceback.format_exc()
        }


def get_tolerance_for_bit_depth(bit_depth: int) -> int:
    """
    Get acceptable pixel difference tolerance for given bit depth.
    
    Args:
        bit_depth: Bit depth (1, 2, or 4)
        
    Returns:
        Maximum acceptable pixel difference
    """
    if bit_depth == 1:
        return 0  # Should be exact for 1-bit
    elif bit_depth == 2:
        return 85  # Allow some quantization error for 2-bit (255/3 = 85)
    elif bit_depth == 4:
        return 17  # Allow small quantization error for 4-bit (255/15 = 17)
    else:
        return 10