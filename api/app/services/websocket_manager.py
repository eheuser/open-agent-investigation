from typing import Dict, Any, List
from fastapi import WebSocket

from ..utils.log_setup import get_logger
from ..utils.security import sanitize_log_message

logger = get_logger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections per investigation."""

    def __init__(self):
        """
        Initializes the connection manager with an empty dictionary mapping investigation IDs (str) to lists of active WebSocket connections. This structure tracks all current WebSocket clients per investigation.
        """
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, investigation_id: str, websocket: WebSocket):
        """
        Accepts a new WebSocket connection and registers it under the specified investigation.

        Parameters
        ----------
        investigation_id: str
            Identifier of the investigation to which the client should be associated.
        websocket: WebSocket
            The incoming WebSocket instance that will be accepted and stored.

        Behavior
        --------
        The method calls `await websocket.accept()` to complete the handshake, ensures an entry exists for the given `investigation_id` in `self.active_connections`, and appends the `websocket` to the list of active connections for that investigation. A log entry is emitted indicating the successful connection.
        """
        await websocket.accept()
        if investigation_id not in self.active_connections:
            self.active_connections[investigation_id] = []
        self.active_connections[investigation_id].append(websocket)
        logger.info(f"WebSocket connected to investigation {sanitize_log_message(investigation_id)}")

    def disconnect(self, investigation_id: str, websocket: WebSocket):
        """
        Remove a WebSocket connection from the manager.

        Parameters
        ----------
        investigation_id: str
            Identifier of the investigation whose group of connections should be updated.
        websocket: WebSocket
            The specific WebSocket instance to remove from the active connections.

        The method checks whether the given `investigation_id` exists in the internal
        `active_connections` mapping. If present, it removes the provided `websocket`
        from the associated list. When the list becomes empty, the entry for that
        investigation ID is deleted entirely. An informational log entry records the
        disconnection event.
        """
        if investigation_id in self.active_connections:
            if websocket in self.active_connections[investigation_id]:
                self.active_connections[investigation_id].remove(websocket)
            if not self.active_connections[investigation_id]:
                del self.active_connections[investigation_id]
        logger.info(f"WebSocket disconnected from investigation {sanitize_log_message(investigation_id)}")

    async def send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """
        Send a JSON-encoded message over the given WebSocket connection.

        Parameters
        ----------
        websocket: WebSocket
            The active WebSocket instance to which the message will be sent.
        message: Dict[str, Any]
            A dictionary representing the payload to transmit; it must be serializable to JSON.

        Raises
        ------
        WebSocketDisconnect
            If the underlying connection is closed or cannot send data.
        """
        await websocket.send_json(message)

    async def broadcast(self, investigation_id: str, message: Dict[str, Any]):
        """
        Broadcast a JSON-serializable message to every active WebSocket connection associated with a given investigation.

        Parameters
        ----------
        investigation_id: str
            The identifier of the investigation whose connections should receive the broadcast.
        message: Dict[str, Any]
            A dictionary representing the payload to be sent as JSON. Must be serialisable by `json.dumps` and compatible with the client’s expected schema.

        Behavior
        --------
        * If no connections are registered for *investigation_id*, the method exits silently.
        * The message is sent concurrently to each connection in the order they were added.
        * Any exception raised while sending to an individual connection is caught, logged at error level, and does not interrupt broadcasting to remaining connections.
        """
        if investigation_id in self.active_connections:
            for connection in self.active_connections[investigation_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to connection: {sanitize_log_message(str(e))}")

    def get_connection_count(self, investigation_id: str) -> int:
        """
        Retrieve the total number of currently active WebSocket connections associated with a given investigation.

        Args:
            investigation_id (str): The unique identifier of the investigation whose connection count is requested.

        Returns:
            int: The count of active connections for the specified investigation. If no connections exist, returns `0`.
        """
        return len(self.active_connections.get(investigation_id, []))


# Global connection manager instance
manager = ConnectionManager()
