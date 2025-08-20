from fastapi import FastAPI
from app.api.intakes import router as intakes_router
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Intake to Ingest MVP")

# Include routers
app.include_router(intakes_router, prefix="/api", tags=["intakes"])

@app.get("/")
async def root():
    return {"message": "Intake to Ingest API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)