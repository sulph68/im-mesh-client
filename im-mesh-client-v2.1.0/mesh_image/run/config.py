"""
Configuration constants for the Meshtastic Image Encoder/Decoder.
"""

# Image size configurations
IMAGE_SIZES = {
    '128x64': (128, 64),
    '96x48': (96, 48),
    '64x64': (64, 64),
    '64x32': (64, 32),
    '48x48': (48, 48),
    '32x32': (32, 32)
}

# Bit depth configurations
SUPPORTED_BIT_DEPTHS = [1, 2, 4]

# Compression method configurations
COMPRESSION_METHODS = {
    'tile_rle': 'T',
    'rle_nibble': 'R',
    'rle_nibble_xor': 'X'
}

# Segment configuration
DEFAULT_SEGMENT_LENGTH = 220
MIN_SEGMENT_LENGTH = 200
MAX_SEGMENT_LENGTH = 300

# Message format patterns
MESSAGE_PREFIX = "IMG"
MESSAGE_PATTERN = r'^IMG(\d+)x(\d+):([TRXtrx])(\d+):(\d+)(?:/(\d+))?:(.+)$'

# Supported image formats
SUPPORTED_IMAGE_FORMATS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')

# Tile configurations
TILE_SIZES = {
    'small': (4, 4),
    'large': (8, 8)
}

# Default tile size for tile-based compression
DEFAULT_TILE_SIZE = TILE_SIZES['large']