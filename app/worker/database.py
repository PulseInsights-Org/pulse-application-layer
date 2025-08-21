"""
Database operations for the extraction worker.
Handles querying ready intakes, updating statuses, and creating memory records.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from supabase import Client
from app.core.models import Intake, Memory, MemoryCreate
from app.core.config import config

logger = logging.getLogger(__name__)

class WorkerDatabase:
    """Database operations for the extraction worker."""
    
    def __init__(self, supabase_client: Client):
        """
        Initialize worker database operations.
        
        Args:
            supabase_client: Supabase client instance
        """
        self.client = supabase_client
    
    async def get_ready_intakes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get intakes that are ready for processing.
        
        Args:
            limit: Maximum number of intakes to return
            
        Returns:
            List of intake records ready for processing
        """
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            
            # Query intakes with status 'ready' and next_retry_at in the past
            result = self.client.table("intakes").select("*").eq(
                "status", "ready"
            ).lte(
                "next_retry_at", current_time
            ).order(
                "next_retry_at", desc=False
            ).limit(limit).execute()
            
            intakes = result.data or []
            logger.info(f"Found {len(intakes)} ready intakes for processing")
            
            return intakes
            
        except Exception as e:
            logger.error(f"Error querying ready intakes: {e}")
            return []
    
    async def claim_intake_for_processing(self, intake_id: str, org_id: str) -> bool:
        """
        Atomically claim an intake for processing by updating status from ready to processing.
        This prevents race conditions when multiple workers try to process the same intake.
        
        Args:
            intake_id: ID of the intake to claim
            org_id: Organization ID for validation
            
        Returns:
            True if successfully claimed, False if already claimed by another worker
        """
        try:
            current_time = datetime.now(timezone.utc).isoformat()
            
            # Atomic update: only update if status is still 'ready'
            result = self.client.table("intakes").update({
                "status": "processing",
                "updated_at": current_time
            }).eq("id", intake_id).eq("org_id", org_id).eq("status", "ready").execute()
            
            # Check if any rows were updated
            if result.data and len(result.data) > 0:
                logger.info(f"Successfully claimed intake {intake_id} for processing")
                return True
            else:
                logger.debug(f"Failed to claim intake {intake_id} - already claimed by another worker")
                return False
                
        except Exception as e:
            logger.error(f"Error claiming intake {intake_id}: {e}")
            return False
    
    async def update_intake_status(
        self, 
        intake_id: str, 
        status: str, 
        error_message: Optional[str] = None,
        attempts: Optional[int] = None,
        next_retry_at: Optional[datetime] = None
    ) -> bool:
        """
        Update intake status and related fields.
        
        Args:
            intake_id: ID of the intake to update
            status: New status to set
            error_message: Error message if status indicates failure
            attempts: Number of processing attempts
            next_retry_at: When to retry next (for error states)
            
        Returns:
            True if update succeeded, False otherwise
        """
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if error_message:
                update_data["last_error"] = error_message
            
            if attempts is not None:
                update_data["attempts"] = attempts
            
            if next_retry_at:
                update_data["next_retry_at"] = next_retry_at.isoformat()
            
            result = self.client.table("intakes").update(update_data).eq("id", intake_id).execute()
            
            if result.data:
                logger.info(f"Updated intake {intake_id} status to {status}")
                return True
            else:
                logger.error(f"Failed to update intake {intake_id} status")
                return False
                
        except Exception as e:
            logger.error(f"Error updating intake {intake_id} status: {e}")
            return False
    
    async def schedule_retry(
        self, 
        intake_id: str, 
        current_attempts: int, 
        error_message: str,
        max_attempts: Optional[int] = None,
        base_delay_seconds: Optional[int] = None
    ) -> bool:
        """
        Schedule an intake for retry with exponential backoff.
        
        Args:
            intake_id: ID of the intake to schedule for retry
            current_attempts: Current number of attempts
            error_message: Error message from the failed attempt
            max_attempts: Maximum number of retry attempts
            base_delay_seconds: Base delay for exponential backoff
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            # Use config defaults if not provided
            if max_attempts is None:
                max_attempts = config.worker_max_retry_attempts
            if base_delay_seconds is None:
                base_delay_seconds = config.worker_base_retry_delay
                
            new_attempts = current_attempts + 1
            
            # Check if we've exceeded max attempts
            if new_attempts >= max_attempts:
                logger.warning(f"Intake {intake_id} exceeded max attempts ({max_attempts}), marking as failed")
                return await self.update_intake_status(
                    intake_id, 
                    "failed_max_attempts", 
                    f"Exceeded maximum attempts ({max_attempts}). Last error: {error_message}",
                    attempts=new_attempts
                )
            
            # Calculate exponential backoff delay
            delay_seconds = base_delay_seconds * (2 ** (new_attempts - 1))
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            
            logger.info(f"Scheduling retry for intake {intake_id} in {delay_seconds} seconds (attempt {new_attempts}/{max_attempts})")
            
            return await self.update_intake_status(
                intake_id,
                "ready",  # Back to ready for retry
                error_message,
                attempts=new_attempts,
                next_retry_at=next_retry
            )
            
        except Exception as e:
            logger.error(f"Error scheduling retry for intake {intake_id}: {e}")
            return False
    
    async def create_memory(self, memory_data: MemoryCreate) -> Optional[str]:
        """
        Create a new memory record from processed intake.
        
        Args:
            memory_data: Memory creation data
            
        Returns:
            Memory ID if successful, None otherwise
        """
        try:
            memory_id = str(uuid.uuid4())
            
            memory_record = {
                "id": memory_id,
                "intake_id": str(memory_data.intake_id),
                "org_id": memory_data.org_id,
                "title": memory_data.title,
                "summary": memory_data.summary,
                "metadata": memory_data.metadata,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            result = self.client.table("memories").insert(memory_record).execute()
            
            if result.data:
                logger.info(f"Created memory {memory_id} for intake {memory_data.intake_id}")
                return memory_id
            else:
                logger.error(f"Failed to create memory for intake {memory_data.intake_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating memory for intake {memory_data.intake_id}: {e}")
            return None
    
    async def get_intake_details(self, intake_id: str, org_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific intake.
        
        Args:
            intake_id: ID of the intake
            org_id: Organization ID for validation
            
        Returns:
            Intake details if found, None otherwise
        """
        try:
            result = self.client.table("intakes").select("*").eq(
                "id", intake_id
            ).eq("org_id", org_id).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            else:
                logger.warning(f"Intake {intake_id} not found for org {org_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching intake {intake_id}: {e}")
            return None
    
    async def get_worker_stats(self) -> Dict[str, Any]:
        """
        Get statistics about worker processing status.
        
        Returns:
            Dictionary with worker statistics
        """
        try:
            stats = {}
            
            # Count intakes by status
            for status in ["ready", "processing", "done", "failed_max_attempts"]:
                result = self.client.table("intakes").select("id", count="exact").eq("status", status).execute()
                stats[f"{status}_count"] = result.count or 0
            
            # Count recent errors (last 24 hours)
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            error_result = self.client.table("intakes").select("id", count="exact").neq(
                "last_error", None
            ).gte("updated_at", yesterday).execute()
            stats["recent_errors_count"] = error_result.count or 0
            
            # Count total memories created
            memory_result = self.client.table("memories").select("id", count="exact").execute()
            stats["total_memories_count"] = memory_result.count or 0
            
            logger.debug(f"Worker stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error fetching worker stats: {e}")
            return {"error": str(e)}
