"""
Session management for multi-tenant Meshtastic client.

Handles separate instances for different nodes with isolated databases.
"""

import uuid
import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

from core.gateway import Gateway
from storage.database import Database
from config.settings import Settings

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages multiple isolated sessions for different Meshtastic nodes.
    
    Each session has its own:
    - Database file
    - Gateway instance
    - Meshtastic connection
    - Node information
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: Dict[str, 'Session'] = {}
        self.cleanup_interval = 3600  # 1 hour
        self.session_timeout = 24 * 60 * 60  # 24 hours
        self.cleanup_task = None
    
    def start(self):
        """Start the session manager background tasks."""
        # Background cleanup will be started when first session is created
        logger.info("Session manager started")
    
    def find_session_by_host_port(self, host: str, port: int) -> Optional[str]:
        """
        Find an existing session for a given host:port.
        
        Returns:
            Session ID if found, None otherwise
        """
        for session_id, session in self.sessions.items():
            if (session.settings.meshtastic.host == host and 
                session.settings.meshtastic.port == port):
                return session_id
        return None
    
    async def create_session(self, meshtastic_host: str, meshtastic_port: int, 
                           session_id: Optional[str] = None,
                           connection_type: str = "tcp",
                           serial_port: Optional[str] = None) -> str:
        """
        Create a new session for a specific Meshtastic node.
        
        If an existing session for the same host:port already exists,
        returns the existing session ID instead of creating a new one.
        
        Args:
            meshtastic_host: Meshtastic TCP host or "serial://<port>"
            meshtastic_port: Meshtastic TCP port (0 for serial)
            session_id: Optional existing session ID to restore
            connection_type: "tcp" or "serial"
            serial_port: Serial device path (e.g., /dev/ttyUSB0)
            
        Returns:
            Session ID
        """
        # If a specific session_id was requested, check if it already exists in memory
        if session_id and session_id in self.sessions:
            existing = self.sessions[session_id]
            logger.info(f"Reusing existing session {session_id} for {meshtastic_host}:{meshtastic_port}")
            existing.last_accessed = datetime.now()
            return session_id

        # Check for existing session with same host:port
        existing_id = self.find_session_by_host_port(meshtastic_host, meshtastic_port)
        if existing_id:
            logger.info(f"Reusing existing session {existing_id} for {meshtastic_host}:{meshtastic_port}")
            session = self.sessions[existing_id]
            session.last_accessed = datetime.now()
            return existing_id
        
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Create session-specific database path
        db_path = f"sessions/session_{session_id}.db"
        Path("sessions").mkdir(exist_ok=True)
        
        # Create session-specific settings
        session_settings = Settings.load()
        session_settings.meshtastic.host = meshtastic_host
        session_settings.meshtastic.port = meshtastic_port
        session_settings.storage.db_path = db_path
        
        # Store connection type in settings for Gateway to use
        session_settings.meshtastic.connection_type = connection_type
        session_settings.meshtastic.serial_port = serial_port
        
        # Create database and gateway for this session
        database = Database(db_path)
        await database.initialize()
        
        gateway = Gateway(session_settings, database)
        
        # Create session
        session = Session(
            id=session_id,
            gateway=gateway,
            database=database,
            settings=session_settings,
            created_at=datetime.now(),
            last_accessed=datetime.now()
        )
        
        self.sessions[session_id] = session
        
        # Start cleanup task if not already running
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        conn_desc = f"serial:{serial_port}" if connection_type == "serial" else f"{meshtastic_host}:{meshtastic_port}"
        logger.info(f"Created session {session_id} for {conn_desc} ({connection_type})")
        return session_id
    
    async def get_session(self, session_id: str) -> Optional['Session']:
        """Get session by ID, updating last accessed time."""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        session.last_accessed = datetime.now()
        
        return session
    
    def get_sessions(self) -> Dict[str, Any]:
        """
        Get information about all active sessions.
        
        Returns:
            Dictionary with session information
        """
        session_info = {}
        for session_id, session in self.sessions.items():
            session_info[session_id] = {
                'id': session_id,
                'meshtastic_host': session.settings.meshtastic.host,
                'meshtastic_port': session.settings.meshtastic.port,
                'created_at': session.created_at.isoformat(),
                'last_accessed': session.last_accessed.isoformat()
            }
        
        return {
            'sessions': session_info,
            'count': len(session_info)
        }
    
    async def close_session(self, session_id: str, delete_data: bool = False) -> bool:
        """Close and cleanup a specific session.
        
        Args:
            session_id: Session to close
            delete_data: If True, also delete the session database file
        """
        if session_id not in self.sessions:
            return False
        
        session = self.sessions[session_id]
        db_path = session.settings.storage.db_path
        
        try:
            # Stop gateway and close database
            if session.gateway.running:
                await session.gateway.stop()
            
            await session.database.close()
            
            # Delete database file if requested
            if delete_data and db_path:
                db_file = Path(db_path)
                if db_file.exists():
                    db_file.unlink()
                    logger.info(f"Deleted session database: {db_path}")
            
            # Remove session
            del self.sessions[session_id]
            
            logger.info(f"Closed session {session_id}")
            return True
            
        except (OSError, RuntimeError, ConnectionError) as e:
            logger.warning(f"Error closing session {session_id}: {e}")
            return False
    
    async def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """List all active sessions with their info."""
        session_info = {}
        
        for session_id, session in self.sessions.items():
            try:
                connection_status = await session.gateway.get_connection_status()
                
                session_info[session_id] = {
                    'id': session_id,
                    'meshtastic_host': session.settings.meshtastic.host,
                    'meshtastic_port': session.settings.meshtastic.port,
                    'connected': connection_status.get('connected', False),
                    'created_at': session.created_at.isoformat(),
                    'last_accessed': session.last_accessed.isoformat(),
                    'database_path': session.settings.storage.db_path
                }
            except (AttributeError, ConnectionError, RuntimeError) as e:
                logger.warning(f"Error getting session {session_id} info: {e}")
                session_info[session_id] = {
                    'id': session_id,
                    'error': str(e)
                }
        
        return session_info
    
    async def cleanup_expired_sessions(self) -> int:
        """Remove sessions that haven't been accessed recently."""
        cutoff_time = datetime.now() - timedelta(seconds=self.session_timeout)
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if session.last_accessed < cutoff_time:
                expired_sessions.append(session_id)
        
        cleaned_count = 0
        for session_id in expired_sessions:
            if await self.close_session(session_id):
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} expired sessions")
        
        return cleaned_count
    
    async def _periodic_cleanup(self):
        """Periodic cleanup task."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except (OSError, RuntimeError) as e:
                logger.warning(f"Error in periodic cleanup: {e}")
    
    async def shutdown(self):
        """Shutdown all sessions and cleanup."""
        logger.info("Shutting down session manager...")
        
        # Cancel cleanup task
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
        
        # Close all sessions
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
        
        logger.info("Session manager shutdown complete")

class Session:
    """
    Individual session for a Meshtastic node connection.
    """
    
    def __init__(self, id: str, gateway: Gateway, database: Database, 
                 settings: Settings, created_at: datetime, last_accessed: datetime):
        self.id = id
        self.gateway = gateway
        self.database = database
        self.settings = settings
        self.created_at = created_at
        self.last_accessed = last_accessed
    
    async def start(self) -> bool:
        """Start the session gateway."""
        try:
            await self.gateway.start()
            return True
        except (ConnectionError, OSError, RuntimeError) as e:
            logger.error(f"Failed to start session {self.id}: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop the session gateway."""
        try:
            await self.gateway.stop()
            return True
        except (ConnectionError, OSError, RuntimeError) as e:
            logger.error(f"Failed to stop session {self.id}: {e}")
            return False