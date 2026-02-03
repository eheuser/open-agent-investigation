import asyncio
import json
import logging
from typing import Dict
from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse
from ..services.log_streaming import get_streaming_handler
from ..utils.log_setup import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/stream")
async def stream_logs():
    """
    Server-Sent Events (SSE) endpoint that streams application logs in real-time.
    
    Clients connect to this endpoint and receive a continuous stream of log entries
    as they are generated. The stream includes recent logs from the circular buffer
    followed by live updates.
    
    Returns:
        StreamingResponse: An SSE stream with content-type 'text/event-stream'
    """
    
    async def event_generator():
        handler = get_streaming_handler()
        queue = asyncio.Queue(maxsize=100)
        
        try:
            # Register this client
            await handler.add_client(queue)
            logger.debug("New log streaming client connected")
            
            # First, send recent logs from the buffer
            recent_logs = handler.get_recent_logs(limit=100)
            for log_entry in recent_logs:
                yield f"data: {json.dumps(log_entry)}\n\n"
            
            # Then stream new logs as they arrive
            while True:
                try:
                    # Wait for new log entry with timeout to allow periodic checks
                    log_entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(log_entry)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
                    
        except asyncio.CancelledError:
            logger.debug("Log streaming client disconnected")
        finally:
            # Unregister this client
            await handler.remove_client(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/recent")
async def get_recent_logs(limit: int = 100):
    """
    Get recent logs from the circular buffer.
    
    Args:
        limit: Maximum number of logs to return (default: 100, max: 1000)
    
    Returns:
        dict: Contains a 'logs' array with recent log entries
    """
    handler = get_streaming_handler()
    
    # Cap the limit at 1000
    limit = min(limit, 1000)
    
    logs = handler.get_recent_logs(limit=limit)
    
    return {
        "logs": logs,
        "total": len(logs),
        "buffer_size": len(handler.log_buffer)
    }


@router.post("/ingest")
async def ingest_log(log_entry: Dict = Body(...)):
    """
    Ingest a log entry from a worker process.
    
    This endpoint receives log entries from worker processes running in separate
    Python processes and adds them to the streaming log buffer.
    
    Args:
        log_entry: Dictionary containing log entry fields (timestamp, level, logger, message, etc.)
    
    Returns:
        dict: Status message
    """
    handler = get_streaming_handler()
    
    # Add to the circular buffer
    handler.log_buffer.append(log_entry)
    
    # Send to all connected streaming clients
    for queue in handler.queues[:]:
        try:
            if not queue.full():
                queue.put_nowait(log_entry)
        except Exception:
            pass
    
    return {"status": "ok"}


__all__ = ["router"]
