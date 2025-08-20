from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import uuid
import os
from supabase import create_client, Client

# Supabase client will be initialized lazily
supabase: Client = None

def get_supabase_client() -> Client:
    global supabase
    if supabase is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        supabase = create_client(supabase_url, supabase_key)
    return supabase

router = APIRouter()

class InitIntakeResponse(BaseModel):
    intake_id: str
    storage_path: str

@router.post("/intakes.init", response_model=InitIntakeResponse)
async def init_intake(
    x_org_id: str = Header(..., alias="x-org-id", description="Organization ID"),
    x_idempotency_key: str = Header(..., alias="x-idempotency-key", description="Idempotency Key")
):
    """
    Initialize a new intake record.
    Returns intake_id and storage_path for file upload.
    """
    try:
        idempotency_key = x_idempotency_key
        
        # Generate intake_id
        intake_id = str(uuid.uuid4())
        
        # Generate storage path according to doc pattern
        storage_path = f"org/{x_org_id}/intake/{intake_id}/raw.txt"
        
        # Insert into database
        result = get_supabase_client().table("intakes").insert({
            "id": intake_id,
            "org_id": x_org_id,
            "status": "initialized",
            "storage_path": storage_path,
            "idempotency_key": idempotency_key
        }).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create intake record")
        
        return InitIntakeResponse(
            intake_id=intake_id,
            storage_path=storage_path
        )
        
    except Exception as e:
        # Handle idempotency - if duplicate, return existing record
        if "duplicate key value" in str(e).lower():
            # Query existing record with same org_id and idempotency_key
            existing = get_supabase_client().table("intakes").select("id, storage_path").eq("org_id", x_org_id).eq("idempotency_key", idempotency_key).execute()
            
            if existing.data:
                record = existing.data[0]
                return InitIntakeResponse(
                    intake_id=record["id"],
                    storage_path=record["storage_path"]
                )
        
        raise HTTPException(status_code=500, detail=f"Error creating intake: {str(e)}")

@router.get("/intakes/{intake_id}")
async def get_intake(
    intake_id: str,
    x_org_id: str = Header(..., alias="x-org-id", description="Organization ID")
):
    """
    Get intake status and details.
    """
    try:
        result = get_supabase_client().table("intakes").select("*").eq("id", intake_id).eq("org_id", x_org_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Intake not found")
        
        return result.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching intake: {str(e)}")