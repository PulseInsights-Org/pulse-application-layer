from fastapi import FastAPI
from app.api.intakes import router as intakes_router
from app.api.uploads import router as uploads_router
from app.api.worker import router as worker_router
from app.core.middleware import tenant_middleware
from dotenv import load_dotenv
from datetime import datetime, timezone
import logging
import signal
import sys
import httpx
from pydantic import BaseModel
import os

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Scooby configuration
SCOOBY_URL = os.getenv("SCOOBY_URL", "http://localhost:8000")

# Import worker manager to auto-start worker
from app.worker import manager as worker_manager

app = FastAPI(title="Intake to Ingest MVP")

# Add middleware for tenant resolution
app.middleware("http")(tenant_middleware)

# Include routers
app.include_router(intakes_router, prefix="/api", tags=["intakes"])
app.include_router(uploads_router, prefix="/api", tags=["uploads"])
app.include_router(worker_router, prefix="/api", tags=["worker"])

class QueryRequest(BaseModel):
    question: str
    stream: bool = True

@app.get("/")
async def root():
    return {"message": "Intake to Ingest API is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.post("/api/scooby/query")
async def scooby_query(request: QueryRequest):
    """
    Query Scooby bot with optional streaming support.
    
    This endpoint acts as a proxy to Scooby's query endpoint,
    allowing the pulse-application-layer to stream responses
    from Scooby to its clients.
    """
    try:
        if request.stream:
            # For streaming, we'll return a streaming response
            from fastapi.responses import StreamingResponse
            from typing import AsyncGenerator
            
            async def stream_from_scooby() -> AsyncGenerator[str, None]:
                """Stream response from Scooby to client in real-time."""
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                        # Start streaming request to Scooby
                        async with client.stream(
                            "POST",
                            f"{SCOOBY_URL}/query",
                            json={
                                "question": request.question,
                                "stream": True
                            },
                            headers={"Content-Type": "application/json"}
                        ) as scooby_response:
                            
                            if scooby_response.status_code != 200:
                                yield f"data: [ERROR] Scooby API error: {scooby_response.status_code}\n\n"
                                return
                            
                            # Stream chunks from Scooby immediately as they arrive
                            async for chunk in scooby_response.aiter_text():
                                if chunk:
                                    # Forward each chunk immediately to the client
                                    yield chunk
                                    
                except Exception as e:
                    logging.error(f"Error in streaming from Scooby: {e}")
                    yield f"data: [ERROR] Streaming error: {str(e)}\n\n"
            
            return StreamingResponse(
                stream_from_scooby(),
                media_type="text/event-stream"
            )
        else:
            # For non-streaming, return complete response
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                scooby_response = await client.post(
                    f"{SCOOBY_URL}/query",
                    json={
                        "question": request.question,
                        "stream": False
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                if scooby_response.status_code == 200:
                    return scooby_response.json()
                else:
                    return {
                        "error": f"Scooby API error: {scooby_response.status_code}",
                        "details": scooby_response.text
                    }
                    
    except Exception as e:
        logging.error(f"Error calling Scooby API: {e}")
        logging.error(f"Error type: {type(e)}")
        logging.error(f"Error details: {repr(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return {"error": f"Internal error: {str(e)}", "error_type": str(type(e))}

@app.post("/api/scooby/stream")
async def scooby_stream_query(request: QueryRequest):
    """
    Dedicated streaming endpoint for Scooby queries.
    
    This endpoint always streams responses from Scooby,
    providing real-time AI responses to clients.
    """
    from fastapi.responses import StreamingResponse
    from typing import AsyncGenerator
    
    async def stream_from_scooby() -> AsyncGenerator[str, None]:
        """Stream response from Scooby to client in real-time."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                # Start streaming request to Scooby
                async with client.stream(
                    "POST",
                    f"{SCOOBY_URL}/query",
                    json={
                        "question": request.question,
                        "stream": True
                    },
                    headers={"Content-Type": "application/json"}
                ) as scooby_response:
                    
                    if scooby_response.status_code != 200:
                        yield f"data: [ERROR] Scooby API error: {scooby_response.status_code}\n\n"
                        return
                    
                    # Stream chunks from Scooby immediately as they arrive
                    async for chunk in scooby_response.aiter_text():
                        if chunk:
                            # Forward each chunk immediately to the client
                            yield chunk
                            
        except Exception as e:
            logging.error(f"Error in streaming from Scooby: {e}")
            yield f"data: [ERROR] Streaming error: {str(e)}\n\n"
    
    return StreamingResponse(
        stream_from_scooby(),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        logging.info(f"Received signal {signum}, shutting down...")
        worker_manager.stop_worker()
        sys.exit(0)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    import uvicorn
    try:
        uvicorn.run(app, host="0.0.0.0", port=8001)
    except KeyboardInterrupt:
        logging.info("FastAPI server interrupted")
        worker_manager.stop_worker()
    finally:
        logging.info("Server shutdown complete")