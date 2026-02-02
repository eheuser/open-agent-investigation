import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.websocket_manager import ConnectionManager


@pytest.mark.unit
class TestConnectionManager:
    """Test WebSocket connection manager."""

    def test_init(self):
        """
        Test ConnectionManager initialization.

        Ensures that a newly instantiated `ConnectionManager` starts with an empty `active_connections` dictionary, verifying the correct default internal state upon creation.
        """
        manager = ConnectionManager()
        assert manager.active_connections == {}

    async def test_connect_new_investigation(self):
        """
        Test that a new investigation connection is properly established: creates a ConnectionManager instance, mocks a websocket, connects it using an investigation ID, verifies the websocket's accept method is called once, and confirms the manager records the websocket under the correct investigation in its active_connections dictionary.
        """
        manager = ConnectionManager()
        websocket = AsyncMock()
        investigation_id = "test-inv-1"

        await manager.connect(investigation_id, websocket)

        websocket.accept.assert_called_once()
        assert investigation_id in manager.active_connections
        assert websocket in manager.active_connections[investigation_id]

    async def test_connect_multiple_to_same_investigation(self):
        """
        Test that the ConnectionManager allows multiple WebSocket connections to be registered under the same investigation identifier. The test creates a fresh manager instance, mocks two separate WebSocket connections, and registers both with identical `investigation_id`. It then verifies that the internal `active_connections` mapping contains exactly two entries for that investigation and that each mock WebSocket object is present in the corresponding connection set.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        investigation_id = "test-inv-1"

        await manager.connect(investigation_id, ws1)
        await manager.connect(investigation_id, ws2)

        assert len(manager.active_connections[investigation_id]) == 2
        assert ws1 in manager.active_connections[investigation_id]
        assert ws2 in manager.active_connections[investigation_id]

    async def test_connect_to_different_investigations(self):
        """
        Test that the connection manager can maintain separate active connections for multiple investigations by connecting distinct WebSocket mocks to different investigation identifiers and verifying each is stored under its respective key.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        inv1 = "test-inv-1"
        inv2 = "test-inv-2"

        await manager.connect(inv1, ws1)
        await manager.connect(inv2, ws2)

        assert len(manager.active_connections) == 2
        assert ws1 in manager.active_connections[inv1]
        assert ws2 in manager.active_connections[inv2]

    def test_disconnect_removes_connection(self):
        """
        Test that calling `disconnect` removes the specified websocket from the manager's active connections for the given investigation, and deletes the investigation entry when no other connections remain.
        """
        manager = ConnectionManager()
        websocket = AsyncMock()
        investigation_id = "test-inv-1"

        # Manually add connection
        manager.active_connections[investigation_id] = [websocket]

        manager.disconnect(investigation_id, websocket)

        assert investigation_id not in manager.active_connections

    def test_disconnect_removes_only_specific_connection(self):
        """
        Test that disconnecting a WebSocket connection removes only the specified socket from the active connections list for a given investigation while leaving other sockets intact. The test sets up a ConnectionManager with two mock websockets under the same investigation ID, calls `disconnect` on one of them, and asserts that the investigation key remains present, the targeted websocket is removed, and the remaining websocket stays in the list.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        investigation_id = "test-inv-1"

        manager.active_connections[investigation_id] = [ws1, ws2]

        manager.disconnect(investigation_id, ws1)

        assert investigation_id in manager.active_connections
        assert ws1 not in manager.active_connections[investigation_id]
        assert ws2 in manager.active_connections[investigation_id]

    def test_disconnect_last_connection_removes_key(self):
        """
        Test that disconnecting the sole active websocket for an investigation removes the investigation entry from the manager's active_connections dictionary. The test sets up a ConnectionManager instance with one mock websocket stored under a specific investigation ID, calls disconnect with that ID and websocket, and asserts that the investigation key is no longer present in active_connections. This verifies proper cleanup of empty connection lists.
        """
        manager = ConnectionManager()
        websocket = AsyncMock()
        investigation_id = "test-inv-1"

        manager.active_connections[investigation_id] = [websocket]

        manager.disconnect(investigation_id, websocket)

        assert investigation_id not in manager.active_connections

    def test_disconnect_nonexistent_investigation(self):
        """
        Test that disconnecting a websocket from an investigation identifier that does not exist does not raise any exceptions. The test creates a fresh ConnectionManager instance and an AsyncMock websocket, calls `manager.disconnect` with a nonexistent investigation ID, and verifies that no error is thrown. This ensures the method safely handles missing investigations.
        """
        manager = ConnectionManager()
        websocket = AsyncMock()

        # Should not raise error
        manager.disconnect("nonexistent", websocket)

    def test_disconnect_nonexistent_websocket(self):
        """
        Test that disconnecting a websocket which is not present in the active connections list does not raise an exception and leaves existing connections unchanged. The manager is pre-populated with one websocket for a given investigation; attempting to remove a different, non-existent websocket should be a no-op, preserving the original connection in the manager's `active_connections` mapping.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        investigation_id = "test-inv-1"

        manager.active_connections[investigation_id] = [ws1]

        # Should not raise error
        manager.disconnect(investigation_id, ws2)

        assert ws1 in manager.active_connections[investigation_id]

    async def test_send_message(self):
        """
        Test that `ConnectionManager.send_message` correctly forwards a JSON-serializable message to the given websocket by invoking its `send_json` coroutine exactly once with the provided payload.\"""
        """
        manager = ConnectionManager()
        websocket = AsyncMock()
        message = {"type": "test", "data": "hello"}

        await manager.send_message(websocket, message)

        websocket.send_json.assert_called_once_with(message)

    async def test_broadcast_to_all_connections(self):
        """
        Test that the `broadcast` coroutine sends the provided message to every WebSocket connection associated with a given investigation ID.

        The test sets up a `ConnectionManager` instance and populates its `active_connections` mapping for a specific `investigation_id` with three mocked WebSocket objects (`ws1`, `ws2`, `ws3`). It then calls `manager.broadcast(investigation_id, message)` and verifies that each mock's `send_json` method was invoked exactly once with the same `message` payload. This ensures that broadcasting reaches all active connections for the investigation.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()
        investigation_id = "test-inv-1"
        message = {"type": "broadcast", "content": "test"}

        manager.active_connections[investigation_id] = [ws1, ws2, ws3]

        await manager.broadcast(investigation_id, message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)

    async def test_broadcast_to_nonexistent_investigation(self):
        """
        Test that broadcasting a message to an investigation identifier with no active connections does not raise an exception. The test creates a fresh ConnectionManager instance, defines a simple message payload, and invokes the broadcast method with a nonexistent investigation ID, asserting that the call completes without error.
        """
        manager = ConnectionManager()
        message = {"type": "test"}

        # Should not raise error
        await manager.broadcast("nonexistent", message)

    async def test_broadcast_handles_send_errors(self):
        """
        Test that the broadcast method continues sending messages to all remaining connections when one connection raises an exception.

        The test sets up a `ConnectionManager` with three mock WebSocket connections for a given investigation ID. The second mock (`ws2`) is configured to raise an exception on `send_json`. After invoking `manager.broadcast`, the test verifies that:
        - No exception propagates from the broadcast call.
        - The first and third connections (`ws1` and `ws3`) still have their `send_json` method called exactly once with the provided message.
        - The failing connection's error is effectively ignored, allowing the broadcast to proceed for other active connections.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        # Make ws2 raise an error
        ws2.send_json.side_effect = Exception("Connection error")

        investigation_id = "test-inv-1"
        message = {"type": "test"}

        manager.active_connections[investigation_id] = [ws1, ws2, ws3]

        await manager.broadcast(investigation_id, message)

        # ws1 and ws3 should still receive the message
        ws1.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)

    def test_get_connection_count(self):
        """
        Test that `ConnectionManager.get_connection_count` returns the correct number of active WebSocket connections for a given investigation identifier. The test creates a `ConnectionManager` instance, populates its `active_connections` dictionary with two mock WebSocket objects under a specific investigation ID, invokes `get_connection_count` with that ID, and asserts that the returned count equals the expected value (2).
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        investigation_id = "test-inv-1"

        manager.active_connections[investigation_id] = [ws1, ws2]

        count = manager.get_connection_count(investigation_id)

        assert count == 2

    def test_get_connection_count_nonexistent(self):
        """
        Test that `get_connection_count` returns `0` when queried for an investigation identifier that has no active connections. The test creates a fresh :class:`ConnectionManager`, requests the connection count for a nonexistent investigation key, and asserts that the returned count equals zero.
        """
        manager = ConnectionManager()

        count = manager.get_connection_count("nonexistent")

        assert count == 0

    def test_get_connection_count_empty_list(self):
        """
        Test that `get_connection_count` returns zero when the specified investigation ID exists in `active_connections` but its associated list of connections is empty. The test creates a fresh `ConnectionManager`, manually sets an empty list for a given investigation ID, invokes `get_connection_count` with that ID, and asserts that the returned count equals 0.
        """
        manager = ConnectionManager()
        investigation_id = "test-inv-1"

        manager.active_connections[investigation_id] = []

        count = manager.get_connection_count(investigation_id)

        assert count == 0

    async def test_multiple_investigations_broadcast_isolation(self):
        """
        Test that broadcasting a message is limited to connections belonging to the specified investigation, ensuring isolation between different investigations' WebSocket groups. The test sets up two separate investigations with distinct mock WebSocket connections, sends a broadcast to one investigation, and verifies that only the corresponding connection receives the JSON payload while the other remains untouched. This confirms that `ConnectionManager.broadcast` correctly targets the intended group without cross-talk.
        """
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        inv1 = "test-inv-1"
        inv2 = "test-inv-2"

        manager.active_connections[inv1] = [ws1]
        manager.active_connections[inv2] = [ws2]

        message = {"type": "test"}
        await manager.broadcast(inv1, message)

        # Only ws1 should receive the message
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_not_called()

    async def test_broadcast_empty_message(self):
        """
        Test broadcasting an empty JSON payload to all active WebSocket connections associated with a specific investigation ID, verifying that each connection's `send_json` method is called exactly once with the empty dictionary.
        """
        manager = ConnectionManager()
        websocket = AsyncMock()
        investigation_id = "test-inv-1"

        manager.active_connections[investigation_id] = [websocket]

        await manager.broadcast(investigation_id, {})

        websocket.send_json.assert_called_once_with({})

    async def test_broadcast_complex_message(self):
        """
        Test that the ConnectionManager correctly broadcasts a complex, nested JSON message to all websockets associated with a given investigation identifier.

        The test performs the following steps:
        - Instantiates a new `ConnectionManager`.
        - Creates an `AsyncMock` websocket and registers it in the manager's `active_connections` dictionary under a specific `investigation_id`.
        - Defines a multi-level `complex_message` containing type, tool result data, a list of results, and additional metadata.
        - Calls `manager.broadcast` with the investigation identifier and the complex message.
        - Asserts that the websocket's `send_json` coroutine was invoked exactly once with the original `complex_message` payload.

        This verifies that `broadcast` can handle arbitrarily nested structures without alteration and correctly routes the message to each connected client for the specified investigation.
        """
        manager = ConnectionManager()
        websocket = AsyncMock()
        investigation_id = "test-inv-1"

        complex_message = {
            "type": "tool_result",
            "data": {
                "tool_name": "search_timeline",
                "results": [
                    {"id": 1, "event": "Login"},
                    {"id": 2, "event": "File access"},
                ],
                "metadata": {
                    "count": 2,
                    "query": "suspicious activity",
                },
            },
        }

        manager.active_connections[investigation_id] = [websocket]

        await manager.broadcast(investigation_id, complex_message)

        websocket.send_json.assert_called_once_with(complex_message)
