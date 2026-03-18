"""Node management routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends

from core.session_manager import Session
from api.models import MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["nodes"])


def create_node_routes(get_session_dep) -> APIRouter:
    """Create node management routes."""

    @router.get("/nodes")
    async def get_nodes(session: Session = Depends(get_session_dep)):
        """Get all known nodes for the session."""
        try:
            nodes = await session.gateway.get_node_list()
            return MessageResponse(
                success=True,
                message="Nodes retrieved successfully",
                data={"nodes": nodes or [], "count": len(nodes) if nodes else 0}
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting nodes: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/nodes/favorites")
    async def get_favorite_nodes(session: Session = Depends(get_session_dep)):
        """Get favorite nodes for the session."""
        try:
            favorites = await session.gateway.get_favorite_nodes()
            return MessageResponse(
                success=True,
                message="Favorite nodes retrieved successfully",
                data={"favorites": favorites, "count": len(favorites)}
            )
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting favorite nodes: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/nodes/{node_id}/favorite")
    async def set_node_favorite(
        node_id: str, favorite: bool = True,
        session: Session = Depends(get_session_dep)
    ):
        """Mark/unmark a node as favorite."""
        try:
            success = await session.gateway.set_node_favorite(node_id, favorite)
            if success:
                return MessageResponse(
                    success=True,
                    message=f"Node {'favorited' if favorite else 'unfavorited'} successfully"
                )
            return MessageResponse(success=False, message="Failed to update node favorite status")
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error setting node favorite: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/nodes/{node_id}")
    async def get_node_detail(node_id: str, session: Session = Depends(get_session_dep)):
        """Get detailed information for a specific node."""
        try:
            nodes = await session.gateway.get_node_list()
            node = next((n for n in (nodes or []) if n.get('id') == node_id or n.get('num') == node_id), None)
            if node is None:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
            return MessageResponse(
                success=True,
                message="Node detail retrieved successfully",
                data={"node": node}
            )
        except HTTPException:
            raise
        except Exception as e:  # API safety net: HTTP 500
            logger.warning(f"Error getting node detail: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
