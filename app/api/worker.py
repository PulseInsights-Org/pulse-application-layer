from fastapi import APIRouter, HTTPException, Header
import logging
from ..core.config import config
from app.worker.manager import get_worker_instance

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/worker/status")
async def worker_status():
    """Get current worker status."""
    try:
        worker = get_worker_instance()
        if worker:
            status = await worker.get_status()
            return status
        else:
            return {
                "worker_status": "not_started",
                "error": "Worker not initialized"
            }
    except Exception as e:
        logger.error(f"Error getting worker status: {e}")
        return {
            "worker_status": "error",
            "error": str(e)
        }

@router.post("/worker/process/{intake_id}")
async def process_intake_manually(
    intake_id: str,
    x_org_name: str = Header(..., alias="x-org-name", description="Organization ID")
):
    """Manually trigger processing of a specific intake."""
    try:
        
        resp = (
            config._get_supabase_client()
            .table("orgs")
            .select("id")
            .eq("org_name", x_org_name)
            .single()
            .execute()
        )

        if not resp.data:
            raise HTTPException(status_code=404, detail=f"Org {x_org_name} not found")

        x_org_id = resp.data["id"]
        
         
        worker = get_worker_instance()
        
        if not worker:
            raise HTTPException(
                status_code=503,
                detail="Worker not available"
            )
        
        success = await worker.process_specific_intake(intake_id, x_org_id)
        
        if success:
            return {
                "message": f"Successfully processed intake {intake_id}",
                "intake_id": intake_id,
                "status": "processed"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to process intake {intake_id}. Check worker logs for details."
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error manually processing intake {intake_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing intake: {str(e)}"
        )

@router.post("/worker/start")
async def start_worker():
    """Start the worker (if not already running)."""
    try:
        from app.worker.manager import start_worker as start_worker_func
        success = start_worker_func()
        
        if success:
            return {
                "message": "Worker started successfully",
                "status": "started"
            }
        else:
            return {
                "message": "Worker is already running",
                "status": "already_running"
            }
    
    except Exception as e:
        logger.error(f"Error starting worker: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start worker: {str(e)}"
        )

@router.post("/worker/stop")
async def stop_worker():
    """Stop the worker."""
    try:
        from app.worker.manager import stop_worker as stop_worker_func
        stop_worker_func()
        
        return {
            "message": "Worker stopped successfully",
            "status": "stopped"
        }
    
    except Exception as e:
        logger.error(f"Error stopping worker: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop worker: {str(e)}"
        )
