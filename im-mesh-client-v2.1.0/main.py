#!/usr/bin/env python3
"""
Im Mesh Client - Multi-Tenant Main Entry Point

Updated main.py to use the simplified startup approach.
Supports HTTPS with self-signed certificates.
Supports both TCP and Serial connections to Meshtastic nodes.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings, setup_logging, generate_self_signed_cert, resolve_ssl_paths
from core.session_manager import SessionManager
from api.rest_api_multitenant import create_rest_api
from api.websocket_api_multitenant import WebSocketAPI

def main():
    """Main application entry point."""
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        settings = Settings.load()
        
        # Resolve SSL paths relative to this script's directory
        script_dir = str(Path(__file__).parent)
        certfile, keyfile = resolve_ssl_paths(settings, base_dir=script_dir)
        
        # Generate self-signed certificate if SSL enabled and certs missing
        ssl_kwargs = {}
        if certfile and keyfile:
            if generate_self_signed_cert(certfile, keyfile):
                ssl_kwargs['ssl_certfile'] = certfile
                ssl_kwargs['ssl_keyfile'] = keyfile
                protocol = "https"
            else:
                logger.warning("SSL certificate generation failed. Falling back to HTTP.")
                protocol = "http"
        else:
            protocol = "http"
        
        logger.info(f"Starting Im Mesh Client (Multi-Tenant) on port {settings.web.port}")
        
        # Initialize session manager
        session_manager = SessionManager(settings)
        session_manager.start()
        logger.info("Session manager initialized")
        
        # Initialize WebSocket API with session manager
        websocket_api = WebSocketAPI(session_manager)
        
        # Create FastAPI application with session manager
        app = create_rest_api(session_manager, websocket_api, settings)
        
        # Register shutdown event to clean up Meshtastic connections
        @app.on_event("shutdown")
        async def shutdown_event():
            logger.info("Shutting down - cleaning up connections...")
            try:
                await websocket_api.shutdown()
            except (ConnectionError, RuntimeError) as e:
                logger.warning(f"Error shutting down WebSocket API: {e}")
            try:
                await session_manager.shutdown()
            except (ConnectionError, RuntimeError) as e:
                logger.warning(f"Error shutting down session manager: {e}")
            logger.info("Cleanup complete")
        
        # Install SIGINT handler to force exit after 5 seconds if graceful fails
        _shutdown_count = 0
        _original_sigint = signal.getsignal(signal.SIGINT)
        
        def _force_shutdown_handler(signum, frame):
            nonlocal _shutdown_count
            _shutdown_count += 1
            if _shutdown_count == 1:
                logger.info("Shutdown requested (Ctrl+C) - stopping server...")
                # Let uvicorn handle the first SIGINT
                if callable(_original_sigint) and _original_sigint is not signal.SIG_DFL:
                    _original_sigint(signum, frame)
                else:
                    raise KeyboardInterrupt
            else:
                logger.warning("Force shutdown (second Ctrl+C)")
                sys.exit(1)
        
        signal.signal(signal.SIGINT, _force_shutdown_handler)
        
        # Import uvicorn for running the server
        import uvicorn
        
        # Start web server
        logger.info(f"Web interface available at {protocol}://{settings.web.host}:{settings.web.port}")
        if ssl_kwargs:
            logger.info("HTTPS enabled with SSL certificate")
        else:
            logger.info("Running in HTTP mode (no SSL)")
        logger.info("Multi-tenant mode: Each browser can connect to different Meshtastic nodes")
        logger.info("Use Ctrl+C to shutdown")
        
        # Run the server with a graceful shutdown timeout
        uvicorn.run(
            app,
            host=settings.web.host,
            port=settings.web.port,
            log_level="info",
            timeout_graceful_shutdown=5,
            **ssl_kwargs
        )
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:  # Top-level: catch-all for fatal startup errors
        logger.exception(f"Application error: {e}")
        raise

if __name__ == "__main__":
    main()
