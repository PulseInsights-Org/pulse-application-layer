"""
Main worker service for processing intakes.
Polls for ready intakes and processes them using the extraction pipeline.
"""

import asyncio
import logging
import signal
import os
from typing import Optional
from datetime import datetime, timezone
from supabase import create_client, Client

from app.worker.database import WorkerDatabase
from app.worker.processor import IntakeProcessor
from app.core.config import config

logger = logging.getLogger(__name__)

class ExtractionWorker:
    """Main worker service for processing intakes."""
    
    def __init__(
        self,
        polling_interval: int = 30,
        max_concurrent_jobs: int = 3,
        supabase_client: Optional[Client] = None
    ):
        """
        Initialize the extraction worker.
        
        Args:
            polling_interval: How often to poll for new intakes (seconds)
            max_concurrent_jobs: Maximum number of concurrent processing jobs
            supabase_client: Optional Supabase client (creates new one if None)
        """
        self.polling_interval = polling_interval
        self.max_concurrent_jobs = max_concurrent_jobs
        self.is_running = False
        self.active_jobs = set()
        
        # Initialize Supabase client
        if supabase_client:
            self.client = supabase_client
        else:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            self.client = create_client(supabase_url, supabase_key)
        
        # Initialize components
        self.db = WorkerDatabase(self.client)
        self.processor = IntakeProcessor(self.client)
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info(f"✅ Extraction worker initialized (polling: {polling_interval}s, max_concurrent: {max_concurrent_jobs})")
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.stop()
        
        # Only set up signal handlers if we're in the main thread
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except ValueError:
            # Signal handlers can only be set from main thread
            logger.debug("Signal handlers not set (not in main thread)")
    
    async def start(self):
        """Start the worker service."""
        if self.is_running:
            logger.warning("Worker is already running")
            return
        
        self.is_running = True
        logger.info("🚀 Starting extraction worker service")
        
        try:
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("Worker main loop cancelled")
            raise  # Re-raise to properly propagate cancellation
        except Exception as e:
            logger.error(f"❌ Worker main loop crashed: {e}", exc_info=True)
        finally:
            self.is_running = False
            logger.info("🛑 Extraction worker service stopped")
    
    def stop(self):
        """Stop the worker service."""
        logger.info("Stopping extraction worker service...")
        self.is_running = False
    
    async def _main_loop(self):
        """Main worker loop that polls for intakes and processes them."""
        last_stats_log = datetime.now(timezone.utc)
        stats_log_interval = config.worker_stats_log_interval
        
        try:
            while self.is_running:
                try:
                    # Log stats periodically
                    now = datetime.now(timezone.utc)
                    if (now - last_stats_log).total_seconds() > stats_log_interval:
                        await self._log_worker_stats()
                        last_stats_log = now
                    
                    # Clean up completed jobs
                    self._cleanup_completed_jobs()
                    
                    # Check if we should still be running
                    if not self.is_running:
                        break
                    
                    # Check if we can process more intakes
                    if len(self.active_jobs) >= self.max_concurrent_jobs:
                        logger.debug(f"At max concurrent jobs ({self.max_concurrent_jobs}), waiting...")
                        # Use shorter sleep when at max capacity to check shutdown more frequently
                        for _ in range(min(self.polling_interval, 5)):
                            if not self.is_running:
                                break
                            await asyncio.sleep(1)
                        continue
                    
                    # Query for ready intakes
                    ready_intakes = await self.db.get_ready_intakes(
                        limit=self.max_concurrent_jobs - len(self.active_jobs)
                    )
                    
                    if not ready_intakes:
                        logger.debug("No ready intakes found, waiting...")
                        # Use shorter sleep to check shutdown more frequently
                        for _ in range(min(self.polling_interval, 5)):
                            if not self.is_running:
                                break
                            await asyncio.sleep(1)
                        continue
                    
                    # Process each ready intake
                    for intake in ready_intakes:
                        if not self.is_running:  # Check if we should stop
                            break
                            
                        if len(self.active_jobs) >= self.max_concurrent_jobs:
                            break
                        
                        # Try to claim the intake for processing
                        intake_id = intake.get("id")
                        org_id = intake.get("org_id")
                        
                        if await self.db.claim_intake_for_processing(intake_id, org_id):
                            # Successfully claimed, start processing
                            task = asyncio.create_task(self._process_intake_safely(intake))
                            self.active_jobs.add(task)
                            logger.info(f"Started processing intake {intake_id} (active jobs: {len(self.active_jobs)})")
                        else:
                            logger.debug(f"Failed to claim intake {intake_id} - already claimed by another worker")
                    
                    # Short sleep but check for shutdown
                    if self.is_running:
                        await asyncio.sleep(1)
                    
                except asyncio.CancelledError:
                    logger.info("Main loop cancelled, shutting down...")
                    self.is_running = False
                    raise  # Re-raise to propagate cancellation
                except Exception as e:
                    logger.error(f"Error in worker main loop: {e}", exc_info=True)
                    # Use shorter sleep on error to check shutdown more frequently
                    for _ in range(min(self.polling_interval, 5)):
                        if not self.is_running:
                            break
                        await asyncio.sleep(1)
        
        finally:
            # Clean up active jobs on shutdown
            logger.info("Cancelling active jobs...")
            for job in self.active_jobs:
                if not job.done():
                    job.cancel()
            
            # Wait for jobs to finish with timeout
            if self.active_jobs:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self.active_jobs, return_exceptions=True), 
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Some jobs didn't finish within timeout")
            
            logger.info("Worker main loop cleanup complete")
    
    async def _process_intake_safely(self, intake_data: dict):
        """
        Safely process an intake with error handling.
        
        Args:
            intake_data: Intake record from database
        """
        intake_id = intake_data.get("id")
        start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(f"🔄 Processing intake {intake_id}")
            success = await self.processor.process_intake(intake_data)
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            if success:
                logger.info(f"✅ Successfully processed intake {intake_id} in {duration:.2f}s")
            else:
                logger.warning(f"⚠️ Failed to process intake {intake_id} after {duration:.2f}s")
                
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            logger.error(f"❌ Error processing intake {intake_id} after {duration:.2f}s: {e}", exc_info=True)
            
            # Try to update the intake status to indicate processing error
            try:
                attempts = intake_data.get("attempts", 0)
                await self.db.schedule_retry(intake_id, attempts, f"Worker processing error: {str(e)}")
            except Exception as update_error:
                logger.error(f"Failed to update intake {intake_id} after processing error: {update_error}")
    
    def _cleanup_completed_jobs(self):
        """Remove completed jobs from the active jobs set."""
        completed_jobs = {job for job in self.active_jobs if job.done()}
        self.active_jobs -= completed_jobs
        
        if completed_jobs:
            logger.debug(f"Cleaned up {len(completed_jobs)} completed jobs")
    
    async def _log_worker_stats(self):
        """Log worker statistics."""
        try:
            stats = await self.db.get_worker_stats()
            
            logger.info(
                f"📊 Worker Stats - "
                f"Ready: {stats.get('ready_count', 0)}, "
                f"Processing: {stats.get('processing_count', 0)}, "
                f"Done: {stats.get('done_count', 0)}, "
                f"Failed: {stats.get('failed_max_attempts_count', 0)}, "
                f"Recent Errors: {stats.get('recent_errors_count', 0)}, "
                f"Total Memories: {stats.get('total_memories_count', 0)}, "
                f"Active Jobs: {len(self.active_jobs)}"
            )
            
        except Exception as e:
            logger.error(f"Error logging worker stats: {e}")
    
    async def get_status(self) -> dict:
        """Get current worker status."""
        try:
            stats = await self.db.get_worker_stats()
            
            return {
                "worker_status": "running" if self.is_running else "stopped",
                "polling_interval": self.polling_interval,
                "max_concurrent_jobs": self.max_concurrent_jobs,
                "active_jobs": len(self.active_jobs),
                "database_stats": stats,
                "uptime_check": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            return {
                "worker_status": "error",
                "error": str(e)
            }
    
    async def process_specific_intake(self, intake_id: str, org_id: str) -> bool:
        """
        Process a specific intake (useful for manual processing or testing).
        
        Args:
            intake_id: ID of the intake to process
            org_id: Organization ID
            
        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Get intake details
            intake_data = await self.db.get_intake_details(intake_id, org_id)
            
            if not intake_data:
                logger.error(f"Intake {intake_id} not found for org {org_id}")
                return False
            
            # Check if intake is in a processable state
            status = intake_data.get("status")
            if status not in ["ready", "error_config_failed", "error_storage_failed", "error_processing_failed"]:
                logger.error(f"Intake {intake_id} is not in a processable state (status: {status})")
                return False
            
            # Try to claim for processing
            if not await self.db.claim_intake_for_processing(intake_id, org_id):
                logger.error(f"Failed to claim intake {intake_id} for processing")
                return False
            
            # Process the intake
            logger.info(f"Manually processing intake {intake_id}")
            return await self.processor.process_intake(intake_data)
            
        except Exception as e:
            logger.error(f"Error manually processing intake {intake_id}: {e}")
            return False

# Singleton worker instance for the application
_worker_instance: Optional[ExtractionWorker] = None

def get_worker() -> ExtractionWorker:
    """Get the singleton worker instance."""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = ExtractionWorker()
    return _worker_instance

async def start_worker():
    """Start the worker service."""
    worker = get_worker()
    await worker.start()

async def stop_worker():
    """Stop the worker service."""
    global _worker_instance
    if _worker_instance:
        _worker_instance.stop()
        # Give it a moment to stop gracefully
        await asyncio.sleep(0.1)

def get_worker_status() -> dict:
    """Get worker status (sync version)."""
    worker = get_worker()
    return asyncio.run(worker.get_status())
