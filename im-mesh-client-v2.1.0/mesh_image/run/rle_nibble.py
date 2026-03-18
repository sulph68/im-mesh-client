"""
RLE with Nibble Packing compression module for Meshtastic images.
Implements the algorithm described in rle_nibble.txt for optimal compression.
"""

import math
from typing import List, Tuple, Optional
import struct


def rle_nibble_encode_pixels(pixels: List[int], use_row_xor: bool = False, width: int = 128) -> bytes:
    """
    Encode pixel data using RLE with nibble packing, optionally with row XOR preprocessing.
    
    Args:
        pixels: Flattened pixel array
        use_row_xor: Whether to apply row XOR preprocessing
        width: Image width for row processing
        
    Returns:
        Compressed bytes
    """
    if use_row_xor and len(pixels) >= width:
        # Apply row XOR preprocessing
        processed_pixels = []
        
        # First row unchanged
        processed_pixels.extend(pixels[:width])
        
        # XOR each subsequent row with the previous row
        for row_idx in range(1, len(pixels) // width):
            start = row_idx * width
            prev_start = (row_idx - 1) * width
            
            for col in range(width):
                current_pixel = pixels[start + col]
                prev_pixel = pixels[prev_start + col]
                xor_pixel = current_pixel ^ prev_pixel
                processed_pixels.append(xor_pixel)
        
        # Add any remaining pixels if not evenly divisible by width
        if len(pixels) % width != 0:
            processed_pixels.extend(pixels[(len(pixels) // width) * width:])
            
        pixels = processed_pixels
    
    # Perform RLE encoding
    runs = []
    if not pixels:
        return b''
    
    current_value = pixels[0]
    run_length = 1
    
    for i in range(1, len(pixels)):
        if pixels[i] == current_value:
            run_length += 1
        else:
            runs.append((current_value, run_length))
            current_value = pixels[i]
            run_length = 1
    
    # Add final run
    runs.append((current_value, run_length))
    
    # Split runs longer than 15 into multiple runs
    split_runs = []
    for value, length in runs:
        while length > 15:
            split_runs.append((value, 15))
            length -= 15
        if length > 0:
            split_runs.append((value, length))
    
    # Pack run lengths and values into nibbles
    packed_data = []
    
    # For each run, encode: [value_nibble, length_nibble, value_nibble, length_nibble, ...]
    for value, length in split_runs:
        # Split large values and lengths into multiple nibbles if needed
        while value > 15:
            packed_data.append(15)  # Max value nibble
            packed_data.append(15)  # Max length nibble  
            value -= 15
            if length > 15:
                length -= 15
            else:
                break
        
        while length > 15:
            packed_data.append(value)
            packed_data.append(15)  # Max length nibble
            length -= 15
            
        if length > 0:
            packed_data.append(value)
            packed_data.append(length)
    
    # Pack two nibbles per byte
    result = []
    for i in range(0, len(packed_data), 2):
        if i + 1 < len(packed_data):
            byte_value = (packed_data[i] << 4) | packed_data[i + 1]
        else:
            # Odd number of nibbles, pad with zero
            byte_value = packed_data[i] << 4
        result.append(byte_value)
    
    return bytes(result)


def rle_nibble_decode_pixels(data: bytes, target_pixels: int, use_row_xor: bool = False, width: int = 128) -> List[int]:
    """
    Decode RLE nibble-packed pixel data.
    
    Args:
        data: Compressed bytes
        target_pixels: Expected number of pixels to decode
        use_row_xor: Whether row XOR preprocessing was used
        width: Image width for row processing
        
    Returns:
        Decoded pixel array
    """
    if not data:
        return []
    
    # Unpack nibbles
    nibbles = []
    for byte_val in data:
        nibbles.append((byte_val >> 4) & 0xF)  # Upper nibble
        nibbles.append(byte_val & 0xF)         # Lower nibble
    
    # Decode runs: [value, length, value, length, ...]
    pixels = []
    i = 0
    
    while i < len(nibbles) - 1 and len(pixels) < target_pixels:
        value = nibbles[i]
        length = nibbles[i + 1]
        
        if length > 0:
            pixels.extend([value] * length)
        
        i += 2
    
    # Trim to exact target size
    pixels = pixels[:target_pixels]
    
    # If row XOR was used, reverse the preprocessing
    if use_row_xor and len(pixels) >= width:
        restored_pixels = []
        
        # First row unchanged
        restored_pixels.extend(pixels[:width])
        
        # Reconstruct each subsequent row
        for row_idx in range(1, len(pixels) // width):
            start = row_idx * width
            prev_start = (row_idx - 1) * width
            
            for col in range(width):
                delta_pixel = pixels[start + col]
                prev_pixel = restored_pixels[prev_start + col]
                original_pixel = delta_pixel ^ prev_pixel
                restored_pixels.append(original_pixel)
        
        # Add any remaining pixels
        if len(pixels) % width != 0:
            restored_pixels.extend(pixels[(len(pixels) // width) * width:])
            
        pixels = restored_pixels
    
    return pixels


def create_rle_nibble_packet(pixels: List[int], width: int, height: int, bit_depth: int, 
                           use_row_xor: bool = False) -> bytes:
    """
    Create a complete RLE nibble packet with header.
    
    Args:
        pixels: Pixel array
        width: Image width
        height: Image height  
        bit_depth: Bit depth (1, 2, or 4)
        use_row_xor: Whether to use row XOR preprocessing
        
    Returns:
        Complete packet bytes
    """
    # Compress pixel data
    compressed_data = rle_nibble_encode_pixels(pixels, use_row_xor, width)
    
    # Create header
    # Magic: "IMG" (3 bytes)
    # Version: 1 (1 byte)
    # Width: (1 byte)
    # Height: (1 byte)
    # Bit depth: (1 byte)
    # Flags: (1 byte) - bit 0 = row XOR enabled
    
    flags = 1 if use_row_xor else 0
    
    header = struct.pack('3sBBBBB', b'IMG', 1, width, height, bit_depth, flags)
    
    return header + compressed_data


def parse_rle_nibble_packet(packet: bytes) -> Tuple[List[int], int, int, int, dict]:
    """
    Parse an RLE nibble packet and decode the image.
    
    Args:
        packet: Complete packet bytes
        
    Returns:
        Tuple of (pixels, width, height, bit_depth, stats)
    """
    if len(packet) < 8:
        raise ValueError("Packet too short for header")
    
    # Parse header
    magic = packet[:3]
    if magic != b'IMG':
        raise ValueError(f"Invalid magic bytes: {magic}")
    
    version = packet[3]
    width = packet[4]
    height = packet[5]
    bit_depth = packet[6]
    flags = packet[7]
    
    use_row_xor = bool(flags & 1)
    
    # Extract compressed data
    compressed_data = packet[8:]
    
    # Decode pixels
    target_pixels = width * height
    pixels = rle_nibble_decode_pixels(compressed_data, target_pixels, use_row_xor, width)
    
    stats = {
        'version': version,
        'flags': flags,
        'use_row_xor': use_row_xor,
        'compressed_size': len(compressed_data),
        'packet_size': len(packet),
        'header_size': 8,
        'compression_ratio': len(compressed_data) / target_pixels if target_pixels > 0 else 0
    }
    
    return pixels, width, height, bit_depth, stats


def calculate_rle_nibble_efficiency(pixels: List[int], use_row_xor: bool = False, width: int = 128) -> float:
    """
    Calculate compression efficiency for RLE nibble encoding.
    
    Args:
        pixels: Input pixels
        use_row_xor: Whether to use row XOR
        width: Image width
        
    Returns:
        Compression ratio (compressed_size / original_size)
    """
    if not pixels:
        return 1.0
    
    compressed = rle_nibble_encode_pixels(pixels, use_row_xor, width)
    return len(compressed) / len(pixels)


def analyze_rle_nibble_patterns(pixels: List[int]) -> dict:
    """
    Analyze pixel data for RLE nibble compression patterns.
    
    Args:
        pixels: Input pixel array
        
    Returns:
        Dictionary with analysis results
    """
    if not pixels:
        return {'runs': 0, 'avg_run_length': 0, 'max_run_length': 0}
    
    runs = []
    current_pixel = pixels[0]
    current_count = 1
    
    for i in range(1, len(pixels)):
        if pixels[i] == current_pixel:
            current_count += 1
        else:
            runs.append(current_count)
            current_pixel = pixels[i]
            current_count = 1
    
    runs.append(current_count)
    
    # Calculate stats
    total_runs = len(runs)
    avg_length = sum(runs) / total_runs if total_runs > 0 else 0
    max_length = max(runs) if runs else 0
    min_length = min(runs) if runs else 0
    
    # Count runs that need splitting (> 15)
    long_runs = sum(1 for r in runs if r > 15)
    split_factor = sum(math.ceil(r / 15) for r in runs) / total_runs if total_runs > 0 else 1
    
    return {
        'total_runs': total_runs,
        'avg_run_length': avg_length,
        'max_run_length': max_length,
        'min_run_length': min_length,
        'long_runs': long_runs,
        'split_factor': split_factor,
        'compression_estimate': len(runs) * 0.5 / len(pixels) if pixels else 1.0
    }