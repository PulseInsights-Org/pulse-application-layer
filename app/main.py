from fastapi import FastAPI
from fastapi import Request, HTTPException, Header, Query
from app.api.intakes import router as intakes_router
from app.api.uploads import router as uploads_router
from app.api.worker import router as worker_router
from app.core.middleware import tenant_middleware
from app.core.config import config
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
# 👇 configure this list for your environments
ALLOWED_ORIGINS = [
   "http://localhost:8080/"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "x-org-name",
        "x-org-id",   
        "x-org-password",
        "x-intake-id",
        "x-idempotency-key",
    ],
)
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

@app.get("/api/memories")
async def get_memories(
    x_org_id: str = Header(..., alias="x-org-id", description="Organization ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Number of records per page")
):
    """Get memories for a specific organization with pagination."""
    try:
        # Calculate offset for pagination
        offset = (page - 1) * page_size
        
        # Get database client directly from config
        supabase_client = config._get_supabase_client()
        
        # Query memories table for the specific org_id using limit and offset
        result = supabase_client.table("memories").select(
            "title, summary, created_at"
        ).eq(
            "org_id", x_org_id
        ).order(
            "created_at", desc=True
        ).limit(page_size).offset(offset).execute()
        
        memories = result.data or []
        
        # Get total count for pagination info
        count_result = supabase_client.table("memories").select(
            "id", count="exact"
        ).eq("org_id", x_org_id).execute()
        
        total_count = count_result.count or 0
        total_pages = (total_count + page_size - 1) // page_size
        
        # Add some debug logging
        logging.info(f"Query: page={page}, page_size={page_size}, offset={offset}")
        logging.info(f"Result: {len(memories)} memories returned")
        logging.info(f"Total count: {total_count}")
        
        return {
            "memories": memories,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
        
    except Exception as e:
        logging.error(f"Error fetching memories for org {x_org_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch memories: {str(e)}"
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