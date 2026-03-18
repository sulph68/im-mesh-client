"""
Image processing services for the Meshtastic Image Encoder/Decoder.
"""

from PIL import Image
from typing import Union, Tuple
from .models import ImageDimensions, CompressionConfig, PreparationStats


class ImageProcessor:
    """Service for image processing operations."""
    
    @staticmethod
    def load_image(image_source: Union[str, object]) -> Image.Image:
        """
        Load image from file path or file-like object.
        
        Args:
            image_source: File path string or file-like object
            
        Returns:
            PIL Image object
        """
        if hasattr(image_source, 'read'):
            # File-like object
            return Image.open(image_source)
        else:
            # File path
            return Image.open(image_source)
    
    @staticmethod
    def normalize_image(image: Image.Image) -> Image.Image:
        """
        Normalize image to RGB format, handling transparency.
        
        Args:
            image: PIL Image object
            
        Returns:
            RGB PIL Image
        """
        if image.mode in ('RGBA', 'LA'):
            # Handle transparency by creating white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'RGBA':
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image, mask=image.split()[-1])
            return background
        elif image.mode != 'RGB':
            return image.convert('RGB')
        return image
    
    @staticmethod
    def resize_with_aspect_ratio(image: Image.Image, dimensions: ImageDimensions) -> Image.Image:
        """
        Resize image to target dimensions using center crop to maintain quality.
        
        Args:
            image: PIL Image object
            dimensions: Target dimensions
            
        Returns:
            Resized PIL Image
        """
        target_ratio = dimensions.aspect_ratio
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
        
        # Crop and resize
        cropped = image.crop((left, top, right, bottom))
        return cropped.resize((dimensions.width, dimensions.height), Image.Resampling.LANCZOS)
    
    @staticmethod
    def quantize_image(image: Image.Image, config: CompressionConfig) -> Image.Image:
        """
        Quantize grayscale image to specified bit depth.
        
        Args:
            image: Grayscale PIL Image
            config: Compression configuration
            
        Returns:
            Quantized PIL Image
        """
        if image.mode != 'L':
            image = image.convert('L')
        
        levels = config.quantization_levels
        
        # Create quantization mapping
        step = 256 // levels
        quantization_map = []
        
        for i in range(256):
            # Map each input value to appropriate output level
            level = min(i // step, levels - 1)
            # Scale back to 0-255 range
            output_value = int((level * 255) / (levels - 1))
            quantization_map.append(output_value)
        
        return image.point(quantization_map)
    
    @classmethod
    def prepare_image_for_encoding(cls, image_source, config: CompressionConfig, 
                                 dimensions: ImageDimensions) -> Tuple[Image.Image, Image.Image, PreparationStats]:
        """
        Complete image preparation pipeline for encoding.
        
        Args:
            image_source: File object or path to image
            config: Compression configuration
            dimensions: Target dimensions
            
        Returns:
            Tuple of (original_image, processed_image, preparation_stats)
        """
        # Load and normalize image
        image = cls.load_image(image_source)
        normalized = cls.normalize_image(image)
        
        # Store original image (normalized but unresized)
        original_image = normalized.copy()
        original_size = image.size
        
        # Resize to target dimensions
        resized = cls.resize_with_aspect_ratio(normalized, dimensions)
        
        # Convert to grayscale and quantize
        grayscale = resized.convert('L')
        quantized = cls.quantize_image(grayscale, config)
        
        # Create statistics
        stats = PreparationStats(
            original_size=original_size,
            target_size=(dimensions.width, dimensions.height),
            original_mode=image.mode,
            bit_depth=config.bit_depth,
            quantization_levels=config.quantization_levels
        )
        
        return original_image, quantized, stats