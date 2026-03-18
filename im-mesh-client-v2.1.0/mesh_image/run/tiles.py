"""
Tile processing module for 8x8 image tiles.
Handles tile compression, deduplication, and palette operations.
"""
import hashlib
from typing import List, Tuple, Dict, Any
import struct


def split_tiles(pixels: List[int], width: int = 128, height: int = 64, tile_size: int = 8) -> List[List[int]]:
    """
    Split image pixels into 8x8 tiles.
    
    Args:
        pixels: Flat list of pixel values
        width: Image width (default 128)
        height: Image height (default 64)
        tile_size: Size of each tile (default 8)
        
    Returns:
        List of tiles, each containing 64 pixels
    """
    tiles = []
    tiles_x = width // tile_size  # 16
    tiles_y = height // tile_size  # 8
    
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            tile = []
            for y in range(tile_size):
                for x in range(tile_size):
                    pixel_x = tx * tile_size + x
                    pixel_y = ty * tile_size + y
                    pixel_index = pixel_y * width + pixel_x
                    tile.append(pixels[pixel_index])
            tiles.append(tile)
    
    return tiles


def compress_tile_palette(tile: List[int]) -> Dict[str, Any]:
    """
    Compress a tile using palette compression if beneficial.
    
    Args:
        tile: Tile pixel data (can be any size: 16, 64, etc.)
        
    Returns:
        Dictionary with compression info:
        - 'type': 'palette' or 'raw'
        - 'data': compressed bytes
        - 'palette': palette values (if palette compression used)
    """
    unique_values = list(set(tile))
    tile_size = len(tile)  # Could be 16 (4x4) or 64 (8x8), etc.
    
    # Use palette compression if <= 4 unique values
    if len(unique_values) <= 4:
        # Sort palette for consistency
        palette = sorted(unique_values)
        palette_size = len(palette)
        
        # Determine bits per pixel
        if palette_size == 1:
            bits_per_pixel = 0  # All same value
        elif palette_size == 2:
            bits_per_pixel = 1
        elif palette_size <= 4:
            bits_per_pixel = 2
        
        # Create palette index mapping
        value_to_index = {val: idx for idx, val in enumerate(palette)}
        
        # Encode pixels using palette indices
        packed_data = []
        if bits_per_pixel == 0:
            # All pixels same value, no data needed
            pass
        elif bits_per_pixel == 1:
            # Pack 8 pixels per byte
            for i in range(0, tile_size, 8):
                byte_val = 0
                for j in range(8):
                    if i + j < tile_size:
                        pixel_val = tile[i + j]
                        index = value_to_index[pixel_val]
                        byte_val |= (index << (7 - j))
                packed_data.append(byte_val)
        elif bits_per_pixel == 2:
            # Pack 4 pixels per byte
            for i in range(0, tile_size, 4):
                byte_val = 0
                for j in range(4):
                    if i + j < tile_size:
                        pixel_val = tile[i + j]
                        index = value_to_index[pixel_val]
                        byte_val |= (index << (6 - j * 2))
                packed_data.append(byte_val)
        
        # Format: [palette_size][palette_values...][packed_pixels...]
        data = bytes([palette_size] + palette + packed_data)
        
        return {
            'type': 'palette',
            'data': data,
            'palette': palette,
            'bits_per_pixel': bits_per_pixel
        }
    else:
        # Use raw encoding (assuming 4-bit values max)
        packed_data = []
        for i in range(0, tile_size, 2):
            byte_val = tile[i] << 4
            if i + 1 < tile_size:
                byte_val |= tile[i + 1]
            packed_data.append(byte_val)
        
        return {
            'type': 'raw',
            'data': bytes(packed_data),
            'palette': None
        }


def decompress_tile_palette(compressed_tile: Dict[str, Any], expected_pixels: int = None) -> List[int]:
    """
    Decompress a palette-compressed tile.
    
    Args:
        compressed_tile: Compressed tile data from compress_tile_palette
        expected_pixels: Expected number of pixels (auto-detect if None)
        
    Returns:
        Tile pixel data
    """
    if compressed_tile['type'] == 'raw':
        # Decompress raw 4-bit data
        data = compressed_tile['data']
        pixels = []
        for byte_val in data:
            pixels.append((byte_val >> 4) & 0xF)
            pixels.append(byte_val & 0xF)
        
        # Trim to expected size if provided
        if expected_pixels:
            return pixels[:expected_pixels]
        return pixels
    
    elif compressed_tile['type'] == 'palette':
        data = compressed_tile['data']
        palette_size = data[0]
        palette = list(data[1:1 + palette_size])
        packed_pixels = data[1 + palette_size:]
        
        bits_per_pixel = compressed_tile['bits_per_pixel']
        pixels = []
        
        if bits_per_pixel == 0:
            # All pixels same value - determine size from expected_pixels or default
            pixel_count = expected_pixels if expected_pixels else 64
            pixels = [palette[0]] * pixel_count
        elif bits_per_pixel == 1:
            # Unpack 8 pixels per byte
            for byte_val in packed_pixels:
                for bit_pos in range(8):
                    if expected_pixels is None or len(pixels) < expected_pixels:
                        index = (byte_val >> (7 - bit_pos)) & 1
                        if index < len(palette):
                            pixels.append(palette[index])
                        else:
                            pixels.append(0)
        elif bits_per_pixel == 2:
            # Unpack 4 pixels per byte
            for byte_val in packed_pixels:
                for pixel_pos in range(4):
                    if expected_pixels is None or len(pixels) < expected_pixels:
                        index = (byte_val >> (6 - pixel_pos * 2)) & 3
                        if index < len(palette):
                            pixels.append(palette[index])
                        else:
                            pixels.append(0)
        
        # Ensure correct length
        if expected_pixels:
            while len(pixels) < expected_pixels:
                pixels.append(0)
            return pixels[:expected_pixels]
        
        return pixels


def deduplicate_tiles(tile_list: List[List[int]]) -> Tuple[List[List[int]], Dict[int, int]]:
    """
    Remove duplicate tiles and create reference map.
    
    Args:
        tile_list: List of 64-pixel tiles
        
    Returns:
        Tuple of (unique_tiles, tile_reference_map)
        tile_reference_map maps original_index -> unique_tile_index
    """
    unique_tiles = []
    tile_hashes = {}
    reference_map = {}
    
    for i, tile in enumerate(tile_list):
        # Create hash of tile data
        tile_hash = hashlib.md5(bytes(tile)).hexdigest()
        
        if tile_hash in tile_hashes:
            # Reference existing tile
            reference_map[i] = tile_hashes[tile_hash]
        else:
            # New unique tile
            unique_index = len(unique_tiles)
            unique_tiles.append(tile)
            tile_hashes[tile_hash] = unique_index
            reference_map[i] = unique_index
    
    return unique_tiles, reference_map


def serialize_tiles(tile_data: Dict[str, Any]) -> bytes:
    """
    Serialize tile data into byte stream.
    
    Args:
        tile_data: Dictionary containing:
            - 'unique_tiles': List of compressed unique tiles
            - 'reference_map': Map of original positions to unique tile indices
            - 'total_tiles': Total number of tiles (128)
            
    Returns:
        Serialized byte stream
    """
    unique_tiles = tile_data['unique_tiles']
    reference_map = tile_data['reference_map']
    total_tiles = tile_data['total_tiles']
    
    result = []
    
    # Header: number of unique tiles
    result.append(len(unique_tiles))
    
    # Serialize unique tiles
    for tile in unique_tiles:
        tile_bytes = tile['data']
        result.append(len(tile_bytes))  # Length prefix
        result.extend(tile_bytes)
    
    # Serialize reference map (128 bytes, each byte is index of unique tile)
    for i in range(total_tiles):
        result.append(reference_map[i])
    
    return bytes(result)


def deserialize_tiles(data: bytes) -> Dict[str, Any]:
    """
    Deserialize tile data from byte stream.
    
    Args:
        data: Serialized byte stream
        
    Returns:
        Dictionary with tile data structure
    """
    if not data:
        return {'unique_tiles': [], 'reference_map': {}, 'total_tiles': 0}
    
    pos = 0
    
    # Read number of unique tiles
    num_unique = data[pos]
    pos += 1
    
    # Read unique tiles
    unique_tiles = []
    for _ in range(num_unique):
        tile_length = data[pos]
        pos += 1
        tile_bytes = data[pos:pos + tile_length]
        pos += tile_length
        
        # Reconstruct tile structure (simplified - just store bytes)
        unique_tiles.append({'data': tile_bytes})
    
    # Read reference map
    total_tiles = len(data) - pos
    reference_map = {}
    for i in range(total_tiles):
        reference_map[i] = data[pos + i]
    
    return {
        'unique_tiles': unique_tiles,
        'reference_map': reference_map,
        'total_tiles': total_tiles
    }


def rebuild_tiles(tile_data: Dict[str, Any]) -> List[List[int]]:
    """
    Rebuild original tile list from compressed data.
    
    Args:
        tile_data: Tile data from deserialize_tiles
        
    Returns:
        List of pixel tiles (size depends on original tile_size)
    """
    unique_tiles = tile_data['unique_tiles']
    reference_map = tile_data['reference_map']
    total_tiles = tile_data['total_tiles']
    tile_size = tile_data.get('tile_size', 8)  # Default to 8 if not specified
    pixels_per_tile = tile_size * tile_size
    
    # First, decompress unique tiles
    decompressed_unique = []
    for tile in unique_tiles:
        # Simple decompression - this would need to match compression format
        # For now, assume raw 4-bit data
        tile_pixels = []
        for byte_val in tile['data']:
            tile_pixels.append((byte_val >> 4) & 0xF)
            tile_pixels.append(byte_val & 0xF)
        
        # Ensure correct tile size
        while len(tile_pixels) < pixels_per_tile:
            tile_pixels.append(0)
        decompressed_unique.append(tile_pixels[:pixels_per_tile])
    
    # Rebuild original tile order
    rebuilt_tiles = []
    for i in range(total_tiles):
        if i in reference_map and reference_map[i] < len(decompressed_unique):
            unique_index = reference_map[i]
            rebuilt_tiles.append(decompressed_unique[unique_index].copy())
        else:
            # Fallback: create black tile of correct size
            rebuilt_tiles.append([0] * pixels_per_tile)
    
    return rebuilt_tiles