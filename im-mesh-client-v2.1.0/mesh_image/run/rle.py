"""
Run Length Encoding (RLE) module for Meshtastic image compression.
Provides efficient compression for repetitive data patterns.
"""

from typing import List, Tuple


def rle_encode(data: bytes) -> bytes:
    """
    Compress data using Run Length Encoding.
    
    Format: [count][value] where count is 1-255, value is byte
    For counts > 255, split into multiple runs.
    
    Args:
        data: Input bytes to compress
        
    Returns:
        RLE compressed bytes
    """
    if not data:
        return b''
    
    result = []
    current_byte = data[0]
    count = 1
    
    for i in range(1, len(data)):
        if data[i] == current_byte and count < 255:
            count += 1
        else:
            # Write current run
            result.append(count)
            result.append(current_byte)
            
            # Start new run
            current_byte = data[i]
            count = 1
    
    # Write final run
    result.append(count)
    result.append(current_byte)
    
    return bytes(result)


def rle_decode(data: bytes) -> bytes:
    """
    Decompress RLE encoded data.
    
    Args:
        data: RLE compressed bytes in format [count][value]...
        
    Returns:
        Decompressed bytes
    """
    if not data:
        return b''
    
    if len(data) % 2 != 0:
        raise ValueError("Invalid RLE data: length must be even")
    
    result = []
    
    for i in range(0, len(data), 2):
        count = data[i]
        value = data[i + 1]
        result.extend([value] * count)
    
    return bytes(result)


def calculate_rle_efficiency(data: bytes) -> float:
    """
    Calculate RLE compression efficiency.
    
    Args:
        data: Original data
        
    Returns:
        Compression ratio (compressed_size / original_size)
    """
    if not data:
        return 1.0
    
    compressed = rle_encode(data)
    return len(compressed) / len(data)


def analyze_rle_patterns(data: bytes) -> dict:
    """
    Analyze data for RLE compression patterns.
    
    Args:
        data: Input data to analyze
        
    Returns:
        Dictionary with analysis results
    """
    if not data:
        return {'runs': 0, 'avg_run_length': 0, 'max_run_length': 0}
    
    runs = []
    current_byte = data[0]
    current_count = 1
    
    for i in range(1, len(data)):
        if data[i] == current_byte:
            current_count += 1
        else:
            runs.append(current_count)
            current_byte = data[i]
            current_count = 1
    
    runs.append(current_count)
    
    return {
        'runs': len(runs),
        'avg_run_length': sum(runs) / len(runs),
        'max_run_length': max(runs),
        'min_run_length': min(runs),
        'total_bytes': len(data)
    }