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
        storage_path = f"org/{x_org_id}/intake/{intake_id}/"
        
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

@router.post("/intakes/{intake_id}/verify")
async def verify_intake(
    intake_id: str,
    x_org_id: str = Header(..., alias="x-org-id", description="Organization ID")
):
    """
    Verify that uploaded file exists in storage and update intake status.
    Changes status from 'uploading' to 'ready' if file exists, or to 'error' if not.
    """
    try:
        # Get intake record
        intake_result = get_supabase_client().table("intakes").select("storage_path, status").eq("id", intake_id).eq("org_id", x_org_id).execute()
        
        if not intake_result.data:
            raise HTTPException(status_code=404, detail="Intake not found")
        
        intake = intake_result.data[0]
        
        # Check if intake is in valid state for verification
        if intake["status"] != "uploading":
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot verify intake with status: {intake['status']}. Expected 'uploading'."
            )
        
        # List files in the intake's storage path to check if any files exist
        try:
            storage_path = intake["storage_path"]
            # Remove trailing slash for proper path handling
            path_for_listing = storage_path.rstrip('/')
            
            files_result = get_supabase_client().storage.from_("intakes-raw").list(path_for_listing)
            
            # Check if any files exist in the directory
            if files_result and len(files_result) > 0:
                # File(s) found - mark as ready
                get_supabase_client().table("intakes").update({
                    "status": "ready",
                    "next_retry_at": "now()"
                }).eq("id", intake_id).execute()
                
                return {
                    "message": "File verification successful",
                    "intake_id": intake_id,
                    "status": "ready",
                    "files_found": len(files_result)
                }
            else:
                # No files found - mark as error
                get_supabase_client().table("intakes").update({
                    "status": "error",
                    "last_error": "No files found in storage path after upload"
                }).eq("id", intake_id).execute()
                
                return {
                    "message": "File verification failed",
                    "intake_id": intake_id,
                    "status": "error",
                    "error": "No files found in storage path"
                }
                
        except Exception as storage_error:
            # Storage access error - mark as error
            error_message = f"Storage verification failed: {str(storage_error)}"
            get_supabase_client().table("intakes").update({
                "status": "error",
                "last_error": error_message
            }).eq("id", intake_id).execute()
            
            return {
                "message": "File verification failed",
                "intake_id": intake_id,
                "status": "error",
                "error": error_message
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying intake: {str(e)}")

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