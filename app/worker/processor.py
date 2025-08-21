"""
Processing orchestrator for the extraction worker.
Coordinates the full processing pipeline for intakes.
"""

import logging
from typing import Dict, Any, Optional
from uuid import UUID
from supabase import Client

from app.core.config import Config
from app.core.models import MemoryCreate
from app.service.pulse_api import PulseAPIClient
from app.worker.database import WorkerDatabase
from app.worker.storage import WorkerStorage

logger = logging.getLogger(__name__)

class IntakeProcessor:
    """Orchestrates the complete processing pipeline for a single intake."""
    
    def __init__(self, supabase_client: Client):
        """
        Initialize the intake processor.
        
        Args:
            supabase_client: Supabase client instance
        """
        self.client = supabase_client
        self.db = WorkerDatabase(supabase_client)
        self.storage = WorkerStorage(supabase_client)
        self.config = Config()
    
    async def process_intake(self, intake_data: Dict[str, Any]) -> bool:
        """
        Process a single intake through the complete pipeline.
        
        Args:
            intake_data: Intake record from database
            
        Returns:
            True if processing succeeded, False otherwise
        """
        intake_id = intake_data.get("id")
        org_id = intake_data.get("org_id")
        storage_path = intake_data.get("storage_path")
        checksum = intake_data.get("checksum")
        attempts = intake_data.get("attempts", 0)
        
        logger.info(f"Starting processing for intake {intake_id} (org: {org_id}, attempt: {attempts + 1})")
        
        try:
            # Step 1: Load tenant configuration
            # Use default org_id from .env if available, otherwise use the intake's org_id
            config_org_id = self.config.default_org_id or org_id
            logger.info(f"Loading tenant configuration for org {config_org_id}")
            
            if not self.config.load_tenant_secrets(config_org_id):
                error_msg = f"Failed to load tenant configuration for org {org_id}"
                logger.error(error_msg)
                await self.db.schedule_retry(intake_id, attempts, error_msg)
                return False
            
            # Step 2: Download and verify content
            logger.info(f"Downloading content from storage path: {storage_path}")
            content = await self.storage.download_and_verify(storage_path, checksum)
            
            if content is None:
                error_msg = f"Failed to download or verify content from {storage_path}"
                logger.error(error_msg)
                await self.db.schedule_retry(intake_id, attempts, error_msg)
                return False
            
            logger.info(f"Successfully downloaded {len(content)} characters of content")
            
            # Step 3: Initialize pulse API client
            logger.info("Initializing pulse API client")
            try:
                pulse_config = self.config.get_pulse_api_config()
                self.pulse_api_client = PulseAPIClient(
                    base_url=pulse_config["base_url"],
                    org_id=org_id
                )
            except Exception as e:
                error_msg = f"Failed to initialize pulse API client: {str(e)}"
                logger.error(error_msg)
                await self.db.schedule_retry(intake_id, attempts, error_msg)
                return False
            
            # Step 4: Process content with pulse API
            logger.info("Processing content with pulse extraction API")
            try:
                extraction_result = await self.pulse_api_client.extract_content(content)
                if extraction_result is None:
                    raise ValueError("Extraction API returned no result")
            except Exception as e:
                error_msg = f"Extraction API processing failed: {str(e)}"
                logger.error(error_msg)
                await self.db.schedule_retry(intake_id, attempts, error_msg)
                return False
            
            # Step 5: Create memory record
            logger.info("Creating memory record")
            
            # Extract information from pulse API response
            # The pulse API returns a different format, so we need to adapt
            title = f"Document from {storage_path}"  # Default title
            summary = f"Processed document with {len(content)} characters"
            
            # Try to get more specific info from the API response
            if extraction_result and isinstance(extraction_result, dict):
                if extraction_result.get("success"):
                    # API was successful, use the message as summary
                    summary = extraction_result.get("message", summary)
                    # Try to extract filename for title
                    filename = extraction_result.get("filename", "")
                    if filename:
                        title = f"Processed: {filename}"
            
            memory_data = MemoryCreate(
                intake_id=UUID(intake_id),
                org_id=org_id,
                title=title,
                summary=summary,
                metadata={
                    "extraction_result": extraction_result,
                    "processing_stats": {
                        "content_length": len(content),
                        "processing_attempts": attempts + 1,
                        "storage_path": storage_path,
                        "checksum": checksum,
                        "pulse_api_used": True
                    }
                }
            )
            
            memory_id = await self.db.create_memory(memory_data)
            
            if memory_id is None:
                error_msg = "Failed to create memory record"
                logger.error(error_msg)
                await self.db.schedule_retry(intake_id, attempts, error_msg)
                return False
            
            # Step 6: Mark intake as done
            logger.info(f"Marking intake {intake_id} as completed")
            success = await self.db.update_intake_status(intake_id, "done")
            
            if success:
                logger.info(f"✅ Successfully processed intake {intake_id} -> memory {memory_id}")
                return True
            else:
                error_msg = "Failed to update intake status to done"
                logger.error(error_msg)
                await self.db.schedule_retry(intake_id, attempts, error_msg)
                return False
        
        except Exception as e:
            error_msg = f"Unexpected error during processing: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await self.db.schedule_retry(intake_id, attempts, error_msg)
            return False
        
        finally:
            # Clean up pulse API client
            if self.pulse_api_client:
                try:
                    await self.pulse_api_client.close()
                except Exception as e:
                    logger.warning(f"Error closing pulse API client: {e}")
    
    async def get_processing_summary(self, intake_id: str) -> Dict[str, Any]:
        """
        Get a summary of processing results for an intake.
        
        Args:
            intake_id: ID of the intake
            
        Returns:
            Dictionary with processing summary
        """
        try:
            # Get intake details
            intake = await self.db.get_intake_details(intake_id, "")  # Empty org_id for summary
            
            if not intake:
                return {"error": "Intake not found"}
            
            summary = {
                "intake_id": intake_id,
                "status": intake.get("status"),
                "attempts": intake.get("attempts", 0),
                "last_error": intake.get("last_error"),
                "created_at": intake.get("created_at"),
                "updated_at": intake.get("updated_at"),
                "storage_path": intake.get("storage_path"),
                "checksum": intake.get("checksum"),
                "size_bytes": intake.get("size_bytes")
            }
            
            # If completed, try to get memory info
            if intake.get("status") == "done":
                try:
                    memory_result = self.client.table("memories").select("id, title, created_at").eq(
                        "intake_id", intake_id
                    ).execute()
                    
                    if memory_result.data:
                        memory = memory_result.data[0]
                        summary["memory"] = {
                            "id": memory.get("id"),
                            "title": memory.get("title"),
                            "created_at": memory.get("created_at")
                        }
                except Exception as e:
                    logger.warning(f"Failed to fetch memory info for intake {intake_id}: {e}")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting processing summary for {intake_id}: {e}")
            return {"error": str(e)}
