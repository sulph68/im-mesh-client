"""
Node storage for Meshtastic Web Client.

Handles storing and managing node information in the database.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .database import Database

logger = logging.getLogger(__name__)

class NodeStore:
    """
    Handles node storage and retrieval operations.
    
    Manages node information including positions, battery status,
    and network metadata.
    """
    
    def __init__(self, database: Database):
        self.db = database
    
    async def upsert_node(self, node_data: Dict[str, Any]) -> None:
        """
        Insert or update node information using SQLite UPSERT.
        
        Args:
            node_data: Dictionary containing node information
        """
        try:
            await self.db.execute("""
                INSERT INTO nodes (
                    node_id, short_name, long_name, hw_model, macaddr,
                    last_seen, battery_level, voltage, channel_utilization,
                    air_util_tx, num_online_local_nodes, position_latitude,
                    position_longitude, position_altitude, position_time,
                    is_neighbor, hop_count, is_favorite
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    short_name = excluded.short_name,
                    long_name = excluded.long_name,
                    hw_model = excluded.hw_model,
                    macaddr = excluded.macaddr,
                    last_seen = excluded.last_seen,
                    battery_level = excluded.battery_level,
                    voltage = excluded.voltage,
                    channel_utilization = excluded.channel_utilization,
                    air_util_tx = excluded.air_util_tx,
                    num_online_local_nodes = excluded.num_online_local_nodes,
                    position_latitude = excluded.position_latitude,
                    position_longitude = excluded.position_longitude,
                    position_altitude = excluded.position_altitude,
                    position_time = excluded.position_time,
                    is_neighbor = excluded.is_neighbor,
                    hop_count = excluded.hop_count,
                    is_favorite = excluded.is_favorite
            """, (
                node_data['node_id'],
                node_data.get('short_name'),
                node_data.get('long_name'),
                node_data.get('hw_model'),
                node_data.get('macaddr'),
                node_data.get('last_seen', datetime.now()),
                node_data.get('battery_level'),
                node_data.get('voltage'),
                node_data.get('channel_utilization'),
                node_data.get('air_util_tx'),
                node_data.get('num_online_local_nodes'),
                node_data.get('position_latitude'),
                node_data.get('position_longitude'),
                node_data.get('position_altitude'),
                node_data.get('position_time'),
                node_data.get('is_neighbor', False),
                node_data.get('hop_count', 0),
                node_data.get('is_favorite', False)
            ))
            
            await self.db.commit()
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to upsert node {node_data.get('node_id')}: {e}")
            await self.db.rollback()
            raise
    
    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node information by ID."""
        try:
            cursor = await self.db.execute("""
                SELECT node_id, short_name, long_name, hw_model, macaddr,
                       last_seen, battery_level, voltage, channel_utilization,
                       air_util_tx, num_online_local_nodes, position_latitude,
                       position_longitude, position_altitude, position_time,
                       is_neighbor, hop_count, is_favorite
                FROM nodes WHERE node_id = ?
            """, (node_id,))
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            return {
                'node_id': row[0],
                'short_name': row[1],
                'long_name': row[2],
                'hw_model': row[3],
                'macaddr': row[4],
                'last_seen': row[5],
                'battery_level': row[6],
                'voltage': row[7],
                'channel_utilization': row[8],
                'air_util_tx': row[9],
                'num_online_local_nodes': row[10],
                'position_latitude': row[11],
                'position_longitude': row[12],
                'position_altitude': row[13],
                'position_time': row[14],
                'is_neighbor': bool(row[15]),
                'hop_count': row[16],
                'is_favorite': bool(row[17])
            }
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to get node {node_id}: {e}")
            return None
    
    async def get_all_nodes(self, include_offline: bool = True,
                           offline_threshold_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get all nodes from the database.
        
        Args:
            include_offline: Whether to include offline nodes
            offline_threshold_hours: Hours after which a node is considered offline
            
        Returns:
            List of node dictionaries
        """
        try:
            query = """
                SELECT node_id, short_name, long_name, hw_model, macaddr,
                       last_seen, battery_level, voltage, channel_utilization,
                       air_util_tx, num_online_local_nodes, position_latitude,
                       position_longitude, position_altitude, position_time,
                       is_neighbor, hop_count, is_favorite
                FROM nodes
            """
            params = []
            
            if not include_offline:
                offline_cutoff = datetime.now() - timedelta(hours=offline_threshold_hours)
                query += " WHERE last_seen > ?"
                params.append(offline_cutoff)
            
            query += " ORDER BY last_seen DESC"
            
            cursor = await self.db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            
            nodes = []
            offline_cutoff = datetime.now() - timedelta(hours=offline_threshold_hours)
            
            for row in rows:
                last_seen = datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5]
                is_online = last_seen and last_seen > offline_cutoff
                
                node = {
                    'node_id': row[0],
                    'short_name': row[1],
                    'long_name': row[2],
                    'hw_model': row[3],
                    'macaddr': row[4],
                    'last_seen': row[5],
                    'battery_level': row[6],
                    'voltage': row[7],
                    'channel_utilization': row[8],
                    'air_util_tx': row[9],
                    'num_online_local_nodes': row[10],
                    'position_latitude': row[11],
                    'position_longitude': row[12],
                    'position_altitude': row[13],
                    'position_time': row[14],
                    'is_neighbor': bool(row[15]),
                    'hop_count': row[16],
                    'is_favorite': bool(row[17]),
                    'is_online': is_online
                }
                nodes.append(node)
            
            return nodes
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to get all nodes: {e}")
            return []
    
    async def get_neighbors(self) -> List[Dict[str, Any]]:
        """Get nodes marked as neighbors."""
        try:
            cursor = await self.db.execute("""
                SELECT node_id, short_name, long_name, last_seen, hop_count
                FROM nodes 
                WHERE is_neighbor = TRUE
                ORDER BY hop_count ASC, last_seen DESC
            """)
            
            rows = await cursor.fetchall()
            
            neighbors = []
            for row in rows:
                neighbor = {
                    'node_id': row[0],
                    'short_name': row[1],
                    'long_name': row[2],
                    'last_seen': row[3],
                    'hop_count': row[4]
                }
                neighbors.append(neighbor)
            
            return neighbors
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to get neighbors: {e}")
            return []
    
    async def update_node_position(self, node_id: str, latitude: float, 
                                  longitude: float, altitude: Optional[int] = None) -> None:
        """Update node position."""
        try:
            await self.db.execute("""
                UPDATE nodes SET
                    position_latitude = ?, position_longitude = ?,
                    position_altitude = ?, position_time = ?
                WHERE node_id = ?
            """, (latitude, longitude, altitude, datetime.now(), node_id))
            
            await self.db.commit()
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to update position for node {node_id}: {e}")
            await self.db.rollback()
    
    async def update_node_battery(self, node_id: str, battery_level: int,
                                 voltage: Optional[float] = None) -> None:
        """Update node battery information."""
        try:
            await self.db.execute("""
                UPDATE nodes SET
                    battery_level = ?, voltage = ?, last_seen = ?
                WHERE node_id = ?
            """, (battery_level, voltage, datetime.now(), node_id))
            
            await self.db.commit()
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to update battery for node {node_id}: {e}")
            await self.db.rollback()
    
    async def mark_node_seen(self, node_id: str) -> None:
        """Update last seen timestamp for a node."""
        try:
            await self.db.execute("""
                UPDATE nodes SET last_seen = ? WHERE node_id = ?
            """, (datetime.now(), node_id))
            
            await self.db.commit()
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to mark node {node_id} as seen: {e}")
    
    async def get_node_stats(self) -> Dict[str, Any]:
        """Get node statistics."""
        try:
            stats = {}
            
            # Total nodes
            cursor = await self.db.execute("SELECT COUNT(*) FROM nodes")
            stats['total_nodes'] = (await cursor.fetchone())[0]
            
            # Online nodes (seen in last 24 hours)
            online_cutoff = datetime.now() - timedelta(hours=24)
            cursor = await self.db.execute("""
                SELECT COUNT(*) FROM nodes WHERE last_seen > ?
            """, (online_cutoff,))
            stats['online_nodes'] = (await cursor.fetchone())[0]
            
            # Neighbor count
            cursor = await self.db.execute("""
                SELECT COUNT(*) FROM nodes WHERE is_neighbor = TRUE
            """)
            stats['neighbor_nodes'] = (await cursor.fetchone())[0]
            
            # Nodes with position data
            cursor = await self.db.execute("""
                SELECT COUNT(*) FROM nodes 
                WHERE position_latitude IS NOT NULL AND position_longitude IS NOT NULL
            """)
            stats['nodes_with_position'] = (await cursor.fetchone())[0]
            
            # Hardware model distribution
            cursor = await self.db.execute("""
                SELECT hw_model, COUNT(*) 
                FROM nodes 
                WHERE hw_model IS NOT NULL
                GROUP BY hw_model 
                ORDER BY COUNT(*) DESC
            """)
            stats['hw_models'] = dict(await cursor.fetchall())
            
            return stats
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to get node stats: {e}")
            return {}
    
    async def cleanup_old_nodes(self, days: int = 30) -> int:
        """Remove nodes not seen in specified days."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor = await self.db.execute("""
                DELETE FROM nodes WHERE last_seen < ?
            """, (cutoff_date,))
            
            await self.db.commit()
            return cursor.rowcount
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to cleanup old nodes: {e}")
            return 0

    async def set_favorite(self, node_id: str, is_favorite: bool = True) -> bool:
        """Mark/unmark a node as favorite."""
        try:
            cursor = await self.db.execute("""
                UPDATE nodes SET is_favorite = ? WHERE node_id = ?
            """, (is_favorite, node_id))
            
            await self.db.commit()
            return cursor.rowcount > 0
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to set favorite for node {node_id}: {e}")
            return False

    async def get_favorites(self) -> List[Dict[str, Any]]:
        """Get all favorite nodes."""
        try:
            cursor = await self.db.execute("""
                SELECT node_id, short_name, long_name, last_seen
                FROM nodes 
                WHERE is_favorite = TRUE
                ORDER BY short_name ASC
            """)
            
            rows = await cursor.fetchall()
            offline_cutoff = datetime.now() - timedelta(hours=24)
            
            favorites = []
            for row in rows:
                last_seen = datetime.fromisoformat(row[3]) if isinstance(row[3], str) else row[3]
                is_online = last_seen and last_seen > offline_cutoff
                
                favorite = {
                    'node_id': row[0],
                    'short_name': row[1],
                    'long_name': row[2],
                    'last_seen': row[3],
                    'is_online': is_online
                }
                favorites.append(favorite)
            
            return favorites
            
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Failed to get favorite nodes: {e}")
            return []