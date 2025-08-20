from fastapi import FastAPI, Request
from app.api.intakes import router as intakes_router
from app.api.uploads import router as uploads_router
from app.core.middleware import tenant_middleware
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Intake to Ingest MVP")

# Add middleware for tenant resolution
app.middleware("http")(tenant_middleware)

# Include routers
app.include_router(intakes_router, prefix="/api", tags=["intakes"])
app.include_router(uploads_router, prefix="/api", tags=["uploads"])

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)