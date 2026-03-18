"""
Fragment reassembler for handling segmented binary messages.

Manages fragment tracking, completion detection, and payload reconstruction.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from .message_router import MessageRouter
from storage.database import Database

logger = logging.getLogger(__name__)

class FragmentReassembler:
    """
    Handles reassembly of fragmented binary messages.
    
    Manages fragment tracking across multiple segments, detects completion,
    and reconstructs the final payload when all fragments are received.
    """
    
    def __init__(self, database: Database, message_router: MessageRouter):
        self.db = database
        self.message_router = message_router
        self.active_fragments: Dict[str, Dict[str, Any]] = {}
        self.cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start the fragment reassembler."""
        # Load active fragments from database
        await self._load_active_fragments()
        
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_fragments())
        logger.info("Fragment reassembler started")
    
    async def stop(self) -> None:
        """Stop the fragment reassembler."""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Fragment reassembler stopped")
    
    async def process_fragment(self, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process an incoming message fragment.
        
        Args:
            message_data: Message data containing fragment information
            
        Returns:
            Complete message data if fragment assembly is complete, None otherwise
        """
        try:
            # Check if this is a fragment
            if not message_data.get('is_fragment', False):
                return None
            
            fragment_id = message_data.get('fragment_id')
            if not fragment_id:
                logger.warning("Fragment message without fragment_id")
                return None
            
            from_node = message_data.get('from_node')
            fragment_key = f"{from_node}:{fragment_id}"
            
            # Get fragment info
            fragment_total = message_data.get('fragment_total', 1)
            fragment_index = message_data.get('fragment_index', 0)
            payload = message_data.get('payload', '')
            
            logger.debug(f"Processing fragment {fragment_index + 1}/{fragment_total} for {fragment_key}")
            
            # Initialize fragment tracking if new
            if fragment_key not in self.active_fragments:
                await self._initialize_fragment(fragment_key, from_node, fragment_total)
            
            fragment_info = self.active_fragments[fragment_key]
            
            # Store this fragment segment
            fragment_info['segments'][fragment_index] = payload
            fragment_info['received_count'] = len([s for s in fragment_info['segments'].values() if s])
            fragment_info['updated_at'] = datetime.now()
            
            # Update database
            await self._update_fragment_in_db(fragment_key, fragment_info)
            
            # Check if fragment is complete
            if fragment_info['received_count'] == fragment_info['total_segments']:
                logger.info(f"Fragment {fragment_key} complete, reassembling...")
                return await self._complete_fragment(fragment_key, fragment_info)
            
            # Notify about fragment progress
            await self.message_router.route_fragment_progress(fragment_key, fragment_info)
            
            return None
            
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error processing fragment: {e}")
            return None
    
    async def _initialize_fragment(self, fragment_key: str, from_node: str, total_segments: int) -> None:
        """Initialize tracking for a new fragment."""
        try:
            fragment_info = {
                'fragment_id': fragment_key.split(':', 1)[1],
                'from_node': from_node,
                'total_segments': total_segments,
                'received_count': 0,
                'segments': {},
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
                'timeout_at': datetime.now() + timedelta(minutes=10)  # 10 minute timeout
            }
            
            self.active_fragments[fragment_key] = fragment_info
            
            # Store in database
            await self.db.execute("""
                INSERT OR REPLACE INTO fragments (
                    fragment_id, from_node, total_segments, received_segments,
                    payload_segments, created_at, updated_at, timeout_at, completed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fragment_info['fragment_id'],
                fragment_info['from_node'],
                fragment_info['total_segments'],
                fragment_info['received_count'],
                json.dumps(fragment_info['segments']),
                fragment_info['created_at'],
                fragment_info['updated_at'],
                fragment_info['timeout_at'],
                False
            ))
            
            await self.db.commit()
            logger.debug(f"Initialized fragment tracking for {fragment_key}")
            
        except (OSError, TypeError, json.JSONDecodeError) as e:
            logger.error(f"Failed to initialize fragment {fragment_key}: {e}")
    
    async def _update_fragment_in_db(self, fragment_key: str, fragment_info: Dict[str, Any]) -> None:
        """Update fragment information in database."""
        try:
            await self.db.execute("""
                UPDATE fragments SET
                    received_segments = ?, payload_segments = ?, updated_at = ?
                WHERE fragment_id = ? AND from_node = ?
            """, (
                fragment_info['received_count'],
                json.dumps(fragment_info['segments']),
                fragment_info['updated_at'],
                fragment_info['fragment_id'],
                fragment_info['from_node']
            ))
            
            await self.db.commit()
            
        except (OSError, TypeError) as e:
            logger.error(f"Failed to update fragment {fragment_key}: {e}")
    
    async def _complete_fragment(self, fragment_key: str, fragment_info: Dict[str, Any]) -> Dict[str, Any]:
        """Complete fragment reassembly and return the reconstructed message."""
        try:
            # Reassemble payload from segments
            segments = fragment_info['segments']
            reconstructed_payload = ""
            
            # Combine segments in order
            for i in range(fragment_info['total_segments']):
                if i in segments:
                    reconstructed_payload += segments[i]
                else:
                    logger.warning(f"Missing segment {i} in fragment {fragment_key}")
                    return None
            
            # Create complete message
            complete_message = {
                'from_node': fragment_info['from_node'],
                'fragment_id': fragment_info['fragment_id'],
                'payload': reconstructed_payload,
                'message_type': 'binary_complete',
                'timestamp': datetime.now(),
                'fragment_count': fragment_info['total_segments'],
                'payload_size': len(reconstructed_payload)
            }
            
            # Mark as complete in database
            await self.db.execute("""
                UPDATE fragments SET completed = TRUE WHERE fragment_id = ? AND from_node = ?
            """, (fragment_info['fragment_id'], fragment_info['from_node']))
            
            await self.db.commit()
            
            # Remove from active tracking
            if fragment_key in self.active_fragments:
                del self.active_fragments[fragment_key]
            
            logger.info(f"Fragment {fragment_key} reassembled successfully ({len(reconstructed_payload)} chars)")
            return complete_message
            
        except (KeyError, TypeError, OSError) as e:
            logger.error(f"Failed to complete fragment {fragment_key}: {e}")
            return None
    
    async def _load_active_fragments(self) -> None:
        """Load active fragments from database on startup."""
        try:
            cursor = await self.db.execute("""
                SELECT fragment_id, from_node, total_segments, received_segments,
                       payload_segments, created_at, updated_at, timeout_at
                FROM fragments 
                WHERE completed = FALSE AND timeout_at > ?
            """, (datetime.now(),))
            
            rows = await cursor.fetchall()
            
            for row in rows:
                fragment_key = f"{row[1]}:{row[0]}"  # from_node:fragment_id
                
                try:
                    segments = json.loads(row[4]) if row[4] else {}
                except json.JSONDecodeError:
                    segments = {}
                
                fragment_info = {
                    'fragment_id': row[0],
                    'from_node': row[1],
                    'total_segments': row[2],
                    'received_count': row[3],
                    'segments': segments,
                    'created_at': row[5],
                    'updated_at': row[6],
                    'timeout_at': datetime.fromisoformat(row[7]) if isinstance(row[7], str) else row[7]
                }
                
                self.active_fragments[fragment_key] = fragment_info
            
            logger.info(f"Loaded {len(self.active_fragments)} active fragments from database")
            
        except (OSError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to load active fragments: {e}")
    
    async def _cleanup_expired_fragments(self) -> None:
        """Background task to clean up expired fragments."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = datetime.now()
                expired_keys = [
                    key for key, info in self.active_fragments.items()
                    if current_time > info['timeout_at']
                ]
                
                if not expired_keys:
                    continue
                
                # Collect info and remove from dict before any await
                expired_items = []
                for key in expired_keys:
                    info = self.active_fragments.pop(key, None)
                    if info:
                        expired_items.append((key, info))
                
                # Now do async DB cleanup (dict is already updated)
                for key, info in expired_items:
                    logger.info(f"Fragment {key} expired, removing")
                    await self.db.execute("""
                        DELETE FROM fragments 
                        WHERE fragment_id = ? AND from_node = ?
                    """, (info['fragment_id'], info['from_node']))
                
                await self.db.commit()
                logger.info(f"Cleaned up {len(expired_items)} expired fragments")
                
            except asyncio.CancelledError:
                break
            except Exception as e:  # Broad: keep cleanup loop alive
                logger.warning(f"Error in fragment cleanup: {e}")
    
    async def get_fragment_status(self, fragment_id: str, from_node: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific fragment."""
        fragment_key = f"{from_node}:{fragment_id}"
        
        if fragment_key in self.active_fragments:
            fragment_info = self.active_fragments[fragment_key]
            return {
                'fragment_id': fragment_info['fragment_id'],
                'from_node': fragment_info['from_node'],
                'total_segments': fragment_info['total_segments'],
                'received_segments': fragment_info['received_count'],
                'progress_percent': (fragment_info['received_count'] / fragment_info['total_segments']) * 100,
                'created_at': fragment_info['created_at'],
                'updated_at': fragment_info['updated_at'],
                'timeout_at': fragment_info['timeout_at'],
                'missing_segments': [
                    i for i in range(fragment_info['total_segments']) 
                    if i not in fragment_info['segments']
                ]
            }
        
        return None
    
    async def get_all_fragments(self) -> List[Dict[str, Any]]:
        """Get status of all active fragments."""
        fragments = []
        
        for fragment_key, fragment_info in self.active_fragments.items():
            status = await self.get_fragment_status(
                fragment_info['fragment_id'], 
                fragment_info['from_node']
            )
            if status:
                fragments.append(status)
        
        return fragments