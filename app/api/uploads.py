from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
import os
from datetime import datetime
from ..core.config import config

router = APIRouter()

@router.post("/upload/file/{intake_id}")
async def upload_file(
    intake_id: str,
    file: UploadFile = File(...),
    x_org_id: str = Header(..., alias="x-org-id", description="Organization ID")
):
    """
    Upload a text file (.txt or .md) for an existing intake.
    Stores the file content in Supabase Storage.
    """
    try:
        # Check if intake exists and belongs to the org
        intake_result = config._get_supabase_client().table("intakes").select("storage_path, status").eq("id", intake_id).eq("org_id", x_org_id).execute()
        
        if not intake_result.data:
            raise HTTPException(status_code=404, detail="Intake not found")
        
        intake = intake_result.data[0]
        
        # Check if intake is in valid state for upload
        if intake["status"] not in ["initialized", "uploading"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot upload to intake with status: {intake['status']}"
            )
        
        # Validate file type
        if not file.filename or not file.filename.lower().endswith(('.txt', '.md')):
            raise HTTPException(
                status_code=400, 
                detail="Only .txt and .md files are allowed"
            )
        
        # Read file content
        content = await file.read()
        
        # Validate file size (10MB limit)
        if len(content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400, 
                detail="File size exceeds 10MB limit"
            )
        
        # Validate encoding
        try:
            content.decode('utf-8')
        except UnicodeDecodeError:
            # Try other common encodings
            for encoding in ['latin-1', 'cp1252']:
                try:
                    content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="Unable to decode file content. Please ensure it's a valid text file."
                )
        
        # Upload to Supabase Storage
        storage_path = f"{intake['storage_path']}{file.filename}"
        
        # Create the file in storage
        storage_result = config._get_supabase_client().storage.from_("intakes-raw").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": "text/plain"}
        )
        
        if not storage_result:
            raise HTTPException(status_code=500, detail="Failed to upload file to storage")
        
        # Update intake status to indicate file is uploaded
        config._get_supabase_client().table("intakes").update({
            "status": "uploading",
            "size_bytes": len(content)
        }).eq("id", intake_id).execute()
        
        return {
            "message": "File uploaded successfully",
            "intake_id": intake_id,
            "storage_path": storage_path,
            "file_size": len(content),
            "file_type": file.filename.split('.')[-1].lower(),
            "original_filename": file.filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@router.post("/upload/text/{intake_id}")
async def upload_pasted_text(
    intake_id: str,
    text_content: str = Form(..., description="Raw text content to upload"),
    x_org_id: str = Header(..., alias="x-org-id", description="Organization ID")
):
    """
    Upload pasted text content for an existing intake.
    Stores the text content in Supabase Storage as a .txt file.
    """
    try:
        # Check if intake exists and belongs to the org
        intake_result = config._get_supabase_client().table("intakes").select("storage_path, status").eq("id", intake_id).eq("org_id", x_org_id).execute()
        
        if not intake_result.data:
            raise HTTPException(status_code=404, detail="Intake not found")
        
        intake = intake_result.data[0]
        
        # Check if intake is in valid state for upload
        if intake["status"] not in ["initialized", "uploading"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot upload to intake with status: {intake['status']}"
            )
        
        # Validate text content
        if not text_content or not text_content.strip():
            raise HTTPException(
                status_code=400, 
                detail="Text content cannot be empty"
            )
        
        # Convert text to bytes for storage
        content = text_content.encode('utf-8')
        
        # Validate content size (10MB limit)
        if len(content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400, 
                detail="Text content exceeds 10MB limit"
            )
        
        # Generate filename for pasted text: org-id-pasted-timestamp.txt
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        original_filename = f"{x_org_id}-pasted-{timestamp}.txt"
        
        # Upload to Supabase Storage
        storage_path = f"{intake['storage_path']}{original_filename}"
        
        # Create the file in storage
        storage_result = config._get_supabase_client().storage.from_("intakes-raw").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": "text/plain"}
        )
        
        if not storage_result:
            raise HTTPException(status_code=500, detail="Failed to upload text to storage")
        
        # Update intake status to indicate content is uploaded
        config._get_supabase_client().table("intakes").update({
            "status": "uploading",
            "size_bytes": len(content)
        }).eq("id", intake_id).execute()
        
        return {
            "message": "Text uploaded successfully",
            "intake_id": intake_id,
            "storage_path": storage_path,
            "content_size": len(content),
            "file_type": "txt",
            "original_filename": original_filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading text: {str(e)}")
