"""
Configuration settings for Meshtastic Web Client.

Handles application settings, logging setup, encoding configuration,
and SSL certificate management.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional

@dataclass
class MeshtasticSettings:
    """Meshtastic connection settings."""
    host: str = "localhost"
    port: int = 4403
    auto_reconnect: bool = True
    reconnect_delay: int = 10
    connection_timeout: int = 10
    connection_type: str = "tcp"  # "tcp" or "serial"
    serial_port: Optional[str] = None  # e.g., "/dev/ttyUSB0"

@dataclass 
class EncodingSettings:
    """Image encoding settings."""
    mode: str = "rle_nibble_xor"  # rle_nibble, tile_rle, rle_nibble_xor
    image_width: int = 64
    image_height: int = 64
    bit_depth: int = 1  # 1, 2, or 4
    segment_length: int = 200
    enable_heatshrink: bool = True
    
@dataclass
class WebSettings:
    """Web interface settings."""
    host: str = "0.0.0.0"  # Bind to all interfaces for external access
    port: int = 8082
    debug: bool = False
    ssl_enabled: bool = True
    ssl_certfile: str = "cert.pem"
    ssl_keyfile: str = "key.pem"
    
@dataclass
class StorageSettings:
    """Storage and database settings."""
    db_path: str = "meshtastic_client.db"

class Settings:
    """Main settings container."""
    
    def __init__(self):
        self.meshtastic = MeshtasticSettings()
        self.encoding = EncodingSettings()
        self.web = WebSettings()
        self.storage = StorageSettings()
        
    @classmethod
    def load(cls, config_file: str = "settings.json") -> "Settings":
        """Load settings from file or create defaults."""
        settings = cls()
        
        config_path = Path(config_file)
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    
                settings._update_from_dict(data)
                logging.info(f"Loaded settings from {config_file}")
                
            except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError) as e:
                logging.warning(f"Error loading settings from {config_file}: {e}")
                logging.info("Using default settings")
        else:
            logging.info(f"No config file found at {config_file}, using defaults")
            
        # Override with environment variables
        settings._load_from_env()
        
        return settings
    
    def save(self, config_file: str = "settings.json") -> None:
        """Save current settings to file."""
        data = {
            'meshtastic': asdict(self.meshtastic),
            'encoding': asdict(self.encoding),
            'web': asdict(self.web),
            'storage': asdict(self.storage)
        }
        
        try:
            with open(config_file, 'w') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Settings saved to {config_file}")
        except (IOError, OSError, TypeError) as e:
            logging.error(f"Error saving settings to {config_file}: {e}")
    
    def _update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update settings from dictionary."""
        section_map = {
            'meshtastic': self.meshtastic,
            'encoding': self.encoding,
            'web': self.web,
            'storage': self.storage,
        }
        for section_name, section_obj in section_map.items():
            if section_name in data:
                for key, value in data[section_name].items():
                    if hasattr(section_obj, key):
                        setattr(section_obj, key, value)
    
    def _load_from_env(self) -> None:
        """Load settings from environment variables."""
        # Meshtastic settings
        if host := os.getenv('MESHTASTIC_HOST'):
            self.meshtastic.host = host
        if port := os.getenv('MESHTASTIC_PORT'):
            self.meshtastic.port = int(port)
            
        # Web settings
        if host := os.getenv('WEB_HOST'):
            self.web.host = host
        if port := os.getenv('WEB_PORT'):
            self.web.port = int(port)
        if debug := os.getenv('WEB_DEBUG'):
            self.web.debug = debug.lower() in ('true', '1', 'yes')
        if ssl_enabled := os.getenv('SSL_ENABLED'):
            self.web.ssl_enabled = ssl_enabled.lower() in ('true', '1', 'yes')
        if ssl_cert := os.getenv('SSL_CERTFILE'):
            self.web.ssl_certfile = ssl_cert
        if ssl_key := os.getenv('SSL_KEYFILE'):
            self.web.ssl_keyfile = ssl_key
            
        # Storage settings  
        if db_path := os.getenv('DB_PATH'):
            self.storage.db_path = db_path
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            'meshtastic': asdict(self.meshtastic),
            'encoding': asdict(self.encoding),
            'web': asdict(self.web),
            'storage': asdict(self.storage)
        }

def setup_logging(level: str = "INFO") -> None:
    """Setup application logging."""
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    # Configure logging format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # File handler
    file_handler = logging.FileHandler('logs/meshtastic_client.log')
    file_handler.setFormatter(formatter)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Silence noisy libraries
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)


def generate_self_signed_cert(certfile: str, keyfile: str) -> bool:
    """
    Generate a self-signed SSL certificate using openssl.
    
    Args:
        certfile: Path to write the certificate PEM file
        keyfile: Path to write the private key PEM file
        
    Returns:
        True if certificate was generated successfully
    """
    certpath = Path(certfile)
    keypath = Path(keyfile)
    
    # Skip if both files already exist
    if certpath.exists() and keypath.exists():
        logging.info(f"SSL certificate already exists: {certfile}")
        return True
    
    logging.info(f"Generating self-signed SSL certificate: {certfile}")
    
    try:
        result = subprocess.run(
            [
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                '-keyout', str(keypath),
                '-out', str(certpath),
                '-days', '365',
                '-nodes',
                '-subj', '/CN=meshtastic-web-client/O=Meshtastic/C=SG'
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logging.error(f"openssl failed: {result.stderr}")
            return False
        
        logging.info(f"SSL certificate generated: {certfile} (valid 365 days)")
        return True
        
    except FileNotFoundError:
        logging.error("openssl not found. Install openssl to generate certificates.")
        return False
    except subprocess.TimeoutExpired:
        logging.error("openssl timed out generating certificate")
        return False
    except (OSError, subprocess.SubprocessError) as e:
        logging.error(f"Failed to generate SSL certificate: {e}")
        return False


def resolve_ssl_paths(settings: 'Settings', base_dir: Optional[str] = None) -> tuple:
    """
    Resolve SSL certificate paths relative to base_dir (or script directory).
    
    Args:
        settings: Application settings
        base_dir: Base directory for relative paths (defaults to script directory)
        
    Returns:
        Tuple of (certfile_path, keyfile_path) as absolute strings, or (None, None) if SSL disabled
    """
    if not settings.web.ssl_enabled:
        return None, None
    
    if base_dir is None:
        base_dir = str(Path(__file__).parent.parent)
    
    certfile = settings.web.ssl_certfile
    keyfile = settings.web.ssl_keyfile
    
    # Resolve relative paths against base_dir
    if not os.path.isabs(certfile):
        certfile = os.path.join(base_dir, certfile)
    if not os.path.isabs(keyfile):
        keyfile = os.path.join(base_dir, keyfile)
    
    return certfile, keyfile


# Default settings instance
default_settings = Settings()