"""
Validation services for input parameters and configurations.
"""

from typing import Any, Dict, List, Union
from .config import IMAGE_SIZES, SUPPORTED_BIT_DEPTHS, COMPRESSION_METHODS, MIN_SEGMENT_LENGTH, MAX_SEGMENT_LENGTH


class ValidationError(ValueError):
    """Custom exception for validation errors."""
    pass


class ParameterValidator:
    """Service for validating input parameters."""
    
    @staticmethod
    def validate_bit_depth(bit_depth: int) -> int:
        """Validate bit depth parameter."""
        if not isinstance(bit_depth, int):
            raise ValidationError(f"Bit depth must be an integer, got {type(bit_depth).__name__}")
        
        if bit_depth not in SUPPORTED_BIT_DEPTHS:
            raise ValidationError(f"Unsupported bit depth: {bit_depth}. Supported: {SUPPORTED_BIT_DEPTHS}")
        
        return bit_depth
    
    @staticmethod
    def validate_image_size(size_string: str) -> tuple:
        """Validate image size string."""
        if not isinstance(size_string, str):
            raise ValidationError(f"Image size must be a string, got {type(size_string).__name__}")
        
        if size_string not in IMAGE_SIZES:
            raise ValidationError(f"Unsupported image size: {size_string}. Supported: {list(IMAGE_SIZES.keys())}")
        
        return IMAGE_SIZES[size_string]
    
    @staticmethod
    def validate_compression_method(method: str) -> str:
        """Validate compression method."""
        if not isinstance(method, str):
            raise ValidationError(f"Compression method must be a string, got {type(method).__name__}")
        
        if method not in COMPRESSION_METHODS:
            raise ValidationError(f"Unsupported compression method: {method}. Supported: {list(COMPRESSION_METHODS.keys())}")
        
        return method
    
    @staticmethod
    def validate_segment_length(length: int) -> int:
        """Validate segment length parameter."""
        if not isinstance(length, int):
            raise ValidationError(f"Segment length must be an integer, got {type(length).__name__}")
        
        if not (MIN_SEGMENT_LENGTH <= length <= MAX_SEGMENT_LENGTH):
            raise ValidationError(f"Segment length must be between {MIN_SEGMENT_LENGTH} and {MAX_SEGMENT_LENGTH}, got {length}")
        
        return length
    
    @staticmethod
    def validate_form_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate complete form data from web request."""
        validated = {}
        
        # Validate bit depth
        bit_depth = form_data.get('bit_depth', 1)
        try:
            bit_depth = int(bit_depth)
            validated['bit_depth'] = ParameterValidator.validate_bit_depth(bit_depth)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid bit depth: {e}")
        
        # Validate image size
        size_string = form_data.get('image_size', '128x64')
        validated['target_width'], validated['target_height'] = ParameterValidator.validate_image_size(size_string)
        validated['image_size'] = size_string
        
        # Validate compression method
        method = form_data.get('compression_method', 'tile_rle')
        validated['compression_method'] = ParameterValidator.validate_compression_method(method)
        
        # Validate segment length
        segment_length = form_data.get('segment_length', 220)
        try:
            segment_length = int(segment_length)
            validated['segment_length'] = ParameterValidator.validate_segment_length(segment_length)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid segment length: {e}")
        
        return validated


class ImageValidator:
    """Service for validating image files and data."""
    
    @staticmethod
    def validate_file_size(file_size: int, max_size_mb: int = 10) -> bool:
        """Validate uploaded file size."""
        max_bytes = max_size_mb * 1024 * 1024
        if file_size > max_bytes:
            raise ValidationError(f"File size {file_size / 1024 / 1024:.1f}MB exceeds maximum {max_size_mb}MB")
        return True
    
    @staticmethod
    def validate_image_format(filename: str) -> bool:
        """Validate image file format by extension."""
        from .config import SUPPORTED_IMAGE_FORMATS
        
        if not filename:
            raise ValidationError("No filename provided")
        
        extension = '.' + filename.lower().split('.')[-1] if '.' in filename else ''
        if extension not in SUPPORTED_IMAGE_FORMATS:
            raise ValidationError(f"Unsupported image format: {extension}. Supported: {SUPPORTED_IMAGE_FORMATS}")
        
        return True
    
    @staticmethod
    def validate_image_dimensions(width: int, height: int, max_dimension: int = 4096) -> bool:
        """Validate image dimensions."""
        if width <= 0 or height <= 0:
            raise ValidationError(f"Invalid image dimensions: {width}x{height}")
        
        if width > max_dimension or height > max_dimension:
            raise ValidationError(f"Image dimensions {width}x{height} exceed maximum {max_dimension}x{max_dimension}")
        
        return True


class MessageValidator:
    """Service for validating Meshtastic messages."""
    
    @staticmethod
    def validate_message_format(message: str) -> bool:
        """Validate message format against expected pattern."""
        from .config import MESSAGE_PATTERN
        import re
        
        if not message or not isinstance(message, str):
            raise ValidationError("Message must be a non-empty string")
        
        if not re.match(MESSAGE_PATTERN, message.strip()):
            raise ValidationError(f"Invalid message format: {message[:50]}...")
        
        return True
    
    @staticmethod
    def validate_segment_sequence(segments: List[str]) -> bool:
        """Validate that segments form a complete sequence."""
        if not segments:
            raise ValidationError("No segments provided")
        
        # Parse segment numbers
        segment_info = []
        for segment in segments:
            try:
                # Extract segment info using message validator
                MessageValidator.validate_message_format(segment)
                # TODO: Extract actual segment numbers
                segment_info.append(segment)
            except ValidationError:
                raise ValidationError(f"Invalid segment format: {segment[:50]}...")
        
        return True