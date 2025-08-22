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

@app.get("/")
async def root():
    return {"message": "Intake to Ingest API is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Intake to Ingest MVP",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/retrieve")
async def retrieve_endpoint(request: QueryRequest):
    """Retrieve information by sending query to Scooby via HTTP."""
    try:
        # Call Scooby's /query endpoint via HTTP
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SCOOBY_URL}/query",
                json={"question": request.question},
                timeout=30.0
            )
            response.raise_for_status()
            scooby_response = response.json()
            
            return {
                "success": True,
                "question": request.question,
                "answer": scooby_response.get("response", "No response from Scooby"),
                "source": "Scooby (HTTP + Gemini WebSocket)"
            }
            
    except httpx.RequestError as e:
        logging.error(f"Error calling Scooby at {SCOOBY_URL}: {e}")
        return {
            "success": False,
            "error": f"Failed to connect to Scooby at {SCOOBY_URL}: {str(e)}"
        }
    except Exception as e:
        logging.error(f"Error in retrieve endpoint: {e}")
        return {
            "success": False,
            "error": f"Internal error: {str(e)}"
        }


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