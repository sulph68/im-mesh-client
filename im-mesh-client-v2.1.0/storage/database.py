"""
Database management for Meshtastic Web Client.

Handles SQLite database connection, schema setup, and migrations.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import aiosqlite
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Database:
    """
    SQLite database manager for Meshtastic Web Client.
    
    Handles connection management, schema setup, and basic database operations.
    """
    
    def __init__(self, db_path: str = "meshtastic_client.db"):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None
        
    async def initialize(self) -> None:
        """Initialize database connection and setup schema."""
        try:
            # Create database directory if needed
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            
            # Connect to database
            self.connection = await aiosqlite.connect(self.db_path)
            
            # Enable foreign keys
            await self.connection.execute("PRAGMA foreign_keys = ON")
            
            # Setup schema
            await self._setup_schema()
            
            # Run migrations if needed
            await self._run_migrations()
            
            await self.connection.commit()
            logger.info(f"Database initialized at {self.db_path}")
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def close(self) -> None:
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    async def _setup_schema(self) -> None:
        """Setup database schema."""
        
        # Nodes table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                short_name TEXT,
                long_name TEXT,
                hw_model TEXT,
                macaddr TEXT,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                battery_level INTEGER,
                voltage REAL,
                channel_utilization REAL,
                air_util_tx REAL,
                num_online_local_nodes INTEGER,
                position_latitude REAL,
                position_longitude REAL,
                position_altitude INTEGER,
                position_time DATETIME,
                is_neighbor BOOLEAN DEFAULT FALSE,
                hop_count INTEGER DEFAULT 0,
                is_favorite BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Fragment reassembly table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS fragments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fragment_id TEXT NOT NULL,
                from_node TEXT NOT NULL,
                total_segments INTEGER NOT NULL,
                received_segments INTEGER DEFAULT 0,
                payload_segments TEXT, -- JSON array of segments
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed BOOLEAN DEFAULT FALSE,
                timeout_at DATETIME,
                UNIQUE(fragment_id, from_node)
            )
        """)
        
        # Settings table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for performance
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_nodes_last_seen 
            ON nodes(last_seen)
        """)
        
        await self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_fragments_id 
            ON fragments(fragment_id, from_node)
        """)
    
    async def _run_migrations(self) -> None:
        """Run database migrations if needed."""
        try:
            # Get current schema version
            version = await self._get_schema_version()
            
            if version < 1:
                # Migration 1: Add any missing columns
                await self._migrate_to_version_1()
                await self._set_schema_version(1)
            
            if version < 2:
                # Migration 2: Drop channels table (now stored client-side)
                await self._migrate_to_version_2()
                await self._set_schema_version(2)
            
            # Add future migrations here
            
        except sqlite3.Error as e:
            logger.error(f"Migration failed: {e}")
            raise
    
    async def _get_schema_version(self) -> int:
        """Get current schema version."""
        try:
            cursor = await self.connection.execute(
                "SELECT value FROM settings WHERE key = 'schema_version'"
            )
            result = await cursor.fetchone()
            if result:
                return int(result[0])
            return 0
        except sqlite3.OperationalError:
            return 0
    
    async def _set_schema_version(self, version: int) -> None:
        """Set schema version."""
        await self.connection.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', ?)",
            (str(version),)
        )
    
    async def _migrate_to_version_1(self) -> None:
        """Migration to version 1."""
        logger.info("Migration to version 1 completed")
    
    async def _migrate_to_version_2(self) -> None:
        """Migration to version 2: Drop channels table (stored client-side now)."""
        try:
            await self.connection.execute("DROP TABLE IF EXISTS channels")
            logger.info("Migration to version 2: dropped channels table")
        except sqlite3.OperationalError as e:
            logger.warning(f"Migration 2 - channels table drop failed (may not exist): {e}")
    
    async def cleanup_old_data(self, days: int = 30) -> None:
        """Clean up old data from database."""
        try:
            # Clean up incomplete fragments older than 1 day
            fragment_cutoff = datetime.now() - timedelta(days=1)
            await self.connection.execute(
                "DELETE FROM fragments WHERE created_at < ? AND completed = FALSE",
                (fragment_cutoff,)
            )
            
            await self.connection.commit()
            logger.info(f"Cleaned up data older than {days} days")
            
        except sqlite3.Error as e:
            logger.error(f"Data cleanup failed: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            stats = {}
            
            # Node count
            cursor = await self.connection.execute("SELECT COUNT(*) FROM nodes")
            stats['total_nodes'] = (await cursor.fetchone())[0]
            
            # Fragment count
            cursor = await self.connection.execute("SELECT COUNT(*) FROM fragments")
            stats['total_fragments'] = (await cursor.fetchone())[0]
            
            # Database file size
            db_path = Path(self.db_path)
            if db_path.exists():
                stats['db_size_bytes'] = db_path.stat().st_size
            else:
                stats['db_size_bytes'] = 0
            
            return stats
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
    async def execute(self, query: str, params: tuple = ()):
        """Execute a database query."""
        if not self.connection:
            raise RuntimeError("Database not initialized")
        return await self.connection.execute(query, params)
    
    async def commit(self) -> None:
        """Commit current transaction."""
        if self.connection:
            await self.connection.commit()
    
    async def rollback(self) -> None:
        """Rollback current transaction."""
        if self.connection:
            await self.connection.rollback()