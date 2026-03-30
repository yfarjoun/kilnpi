"""WebSocket endpoint for real-time status broadcasts."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.poller import ControllerState

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared set of active connections
_connections: set[WebSocket] = set()

# Reference to the shared state — set by main.py at startup
_state: ControllerState | None = None


def set_state(state: ControllerState) -> None:
    global _state
    _state = state


def client_count() -> int:
    """Return the number of active WebSocket clients."""
    return len(_connections)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    logger.info("WebSocket client connected (%d total)", len(_connections))
    try:
        while True:
            # Keep connection alive; ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        logger.info("WebSocket client disconnected (%d total)", len(_connections))


async def broadcast_loop(state: ControllerState, power_state=None, interval: float = 2.0) -> None:
    """Continuously broadcast controller state to all WebSocket clients."""
    set_state(state)
    while True:
        if _connections:
            snapshot = state.snapshot()
            if power_state is not None:
                snapshot.update(power_state.snapshot())
            data = json.dumps(snapshot)
            dead: list[WebSocket] = []
            for ws_conn in list(_connections):
                try:
                    await ws_conn.send_text(data)
                except Exception:
                    dead.append(ws_conn)
            for ws_conn in dead:
                _connections.discard(ws_conn)
        await asyncio.sleep(interval)
