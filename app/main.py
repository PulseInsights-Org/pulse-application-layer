from fastapi import FastAPI
from fastapi import Request
from app.api.intakes import router as intakes_router
from app.api.uploads import router as uploads_router
from app.api.worker import router as worker_router
from app.core.middleware import tenant_middleware
from dotenv import load_dotenv
from datetime import datetime, timezone
import logging
import signal
import sys
from pydantic import BaseModel
from app.worker import manager as worker_manager
from app.service.pulse import PulseLive
from app.core.tools import GeminiTools


load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="Intake to Ingest MVP")
app.middleware("http")(tenant_middleware)
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
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.post("/api/query")
async def scooby_query(internal: Request, request: QueryRequest):
    """
    Query PulseLive (Gemini) with streaming support.
    
    This endpoint uses the PulseLive class to get responses from Gemini
    with tool integration for Pinecone and Neo4j queries.
    """
    try:
        tools = GeminiTools(internal.state.secrets)
        model = PulseLive(tools=tools)
        response = await model.connect_to_gemini(request.question)
        
        return {
            "response": response,
            "status": "success",
            "question": request.question
        }
        
    except Exception as e:
        logging.error(f"Error in Gemini query: {e}")
        return {
            "error": f"Failed to process query: {str(e)}",
            "status": "error",
            "question": request.question
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