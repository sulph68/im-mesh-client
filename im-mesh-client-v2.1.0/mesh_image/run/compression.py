"""
Compression strategies for different encoding methods.
"""

from abc import ABC, abstractmethod
from PIL import Image
from typing import Tuple, Dict, Any
from .models import CompressionConfig, CompressionStats
from .tiles import split_tiles, compress_tile_palette, deduplicate_tiles, serialize_tiles
from .rle import rle_encode
from .rle_nibble import (rle_nibble_encode_pixels, create_rle_nibble_packet, 
                        calculate_rle_nibble_efficiency, analyze_rle_nibble_patterns)


class CompressionStrategy(ABC):
    """Abstract base class for compression strategies."""
    
    @abstractmethod
    def compress(self, image: Image.Image, config: CompressionConfig) -> Tuple[bytes, CompressionStats]:
        """
        Compress image using this strategy.
        
        Args:
            image: PIL Image to compress
            config: Compression configuration
            
        Returns:
            Tuple of (compressed_data, compression_stats)
        """
        pass
    
    @property
    @abstractmethod
    def method_name(self) -> str:
        """Get the method name for this strategy."""
        pass


class TileRLEStrategy(CompressionStrategy):
    """Tile + RLE compression strategy."""
    
    @property
    def method_name(self) -> str:
        return "tile_rle"
    
    def compress(self, image: Image.Image, config: CompressionConfig) -> Tuple[bytes, CompressionStats]:
        """Compress using tile + RLE method."""
        # Convert image to pixel list
        pixels = list(image.getdata())
        
        # Convert from 0-255 to 0-(levels-1) range
        max_val = config.quantization_levels - 1
        converted_pixels = [round(pixel * max_val / 255.0) for pixel in pixels]
        
        # Split into tiles
        tiles = split_tiles(converted_pixels, image.width, image.height)
        
        # Compress each tile with palette compression
        compressed_tiles = []
        for tile in tiles:
            compressed_tile = compress_tile_palette(tile)
            compressed_tiles.append(compressed_tile)
        
        # Deduplicate tiles  
        unique_tiles, reference_map = deduplicate_tiles([tile['data'] for tile in compressed_tiles])
        
        # Calculate tile parameters
        tile_size = 8 if image.width >= 64 else 4
        tiles_x = image.width // tile_size
        tiles_y = image.height // tile_size
        
        # Create proper tile data structure for serialization
        tile_data = {
            'unique_tiles': [{'data': tile} for tile in unique_tiles],
            'reference_map': reference_map,
            'total_tiles': len(tiles),
            'tile_size': tile_size,
            'tiles_x': tiles_x,
            'tiles_y': tiles_y
        }
        
        # Serialize and apply RLE compression
        from .rle import rle_encode
        serialized_data = serialize_tiles(tile_data)
        compressed_data = rle_encode(serialized_data)
        
        # Calculate compression ratio
        original_size = image.width * image.height * config.bit_depth / 8
        compression_ratio = len(compressed_data) / original_size
        
        stats = CompressionStats(
            compression_method=self.method_name,
            compression_ratio=compression_ratio,
            unique_tiles=len(unique_tiles),
            total_tiles=len(tiles),
            base64_encoded_chars=0,  # Will be set later
            uses_heatshrink=config.use_heatshrink
        )
        
        return compressed_data, stats


class RLENibbleStrategy(CompressionStrategy):
    """RLE Nibble compression strategy."""
    
    @property
    def method_name(self) -> str:
        return "rle_nibble"
    
    def compress(self, image: Image.Image, config: CompressionConfig, dimensions=None) -> Tuple[bytes, CompressionStats]:
        """Compress using RLE nibble method."""
        # Expect a processed image (grayscale, quantized, correct size)
        # Convert image to pixel list
        pixels = list(image.getdata())
        
        # Convert from 0-255 quantized values to 0-(levels-1) range
        # The image has already been quantized, but still in 0-255 scale
        max_val = config.quantization_levels - 1
        if max_val == 0:
            # Special case for 1-bit
            converted_pixels = [1 if pixel > 127 else 0 for pixel in pixels]
        else:
            converted_pixels = [round(pixel * max_val / 255.0) for pixel in pixels]
        
        # Get dimensions from image
        width, height = image.width, image.height
        
        # Apply RLE nibble encoding
        compressed_data = create_rle_nibble_packet(converted_pixels, width, height, config.bit_depth, use_row_xor=False)
        
        # Calculate compression ratio
        original_size = len(pixels) * config.bit_depth / 8
        compression_ratio = len(compressed_data) / original_size
        
        stats = CompressionStats(
            compression_method=self.method_name,
            compression_ratio=compression_ratio,
            unique_tiles=None,  # N/A for pixel-stream methods
            total_tiles=None,   # N/A for pixel-stream methods
            base64_encoded_chars=0,  # Will be set later
            uses_heatshrink=config.use_heatshrink
        )
        
        return compressed_data, stats


class RLENibbleXORStrategy(CompressionStrategy):
    """RLE Nibble XOR compression strategy."""
    
    @property
    def method_name(self) -> str:
        return "rle_nibble_xor"
    
    def compress(self, image: Image.Image, config: CompressionConfig) -> Tuple[bytes, CompressionStats]:
        """Compress using RLE nibble XOR method."""
        # Convert image to pixel array
        pixels = list(image.getdata())
        width, height = image.size
        
        # Convert from 0-255 to 0-(levels-1) range
        max_val = config.quantization_levels - 1
        converted_pixels = [round(pixel * max_val / 255.0) for pixel in pixels]
        
        # Let create_rle_nibble_packet handle the XOR preprocessing
        compressed_data = create_rle_nibble_packet(converted_pixels, width, height, config.bit_depth, use_row_xor=True)
        
        # Calculate compression ratio
        original_size = len(pixels) * config.bit_depth / 8
        compression_ratio = len(compressed_data) / original_size
        
        stats = CompressionStats(
            compression_method=self.method_name,
            compression_ratio=compression_ratio,
            unique_tiles=None,  # N/A for pixel-stream methods
            total_tiles=None,   # N/A for pixel-stream methods
            base64_encoded_chars=0,  # Will be set later
            uses_heatshrink=config.use_heatshrink
        )
        
        return compressed_data, stats


class CompressionFactory:
    """Factory for creating compression strategies."""
    
    _strategies = {
        'tile_rle': TileRLEStrategy,
        'rle_nibble': RLENibbleStrategy,
        'rle_nibble_xor': RLENibbleXORStrategy
    }
    
    @classmethod
    def get_strategy(cls, method: str) -> CompressionStrategy:
        """Get compression strategy for method."""
        if method not in cls._strategies:
            raise ValueError(f"Unknown compression method: {method}")
        return cls._strategies[method]()