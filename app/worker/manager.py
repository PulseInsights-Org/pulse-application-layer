"""
Worker management module.
Handles starting, stopping, and managing the extraction worker.
"""

import asyncio
import logging
import threading
import atexit
from typing import Optional

from app.worker.service import ExtractionWorker
from app.core.config import config

logger = logging.getLogger(__name__)

# Global worker state
_worker_instance: Optional[ExtractionWorker] = None
_worker_thread: Optional[threading.Thread] = None
_worker_stopped = False

def get_worker_instance() -> Optional[ExtractionWorker]:
    """Get the current worker instance."""
    global _worker_instance
    return _worker_instance

def start_worker() -> bool:
    """
    Start the extraction worker in a background thread.
    
    Returns:
        True if worker was started, False if already running
    """
    global _worker_instance, _worker_thread, _worker_stopped
    
    if _worker_instance and _worker_instance.is_running:
        logger.info("Worker is already running")
        return False
    
    # Reset stopped flag
    _worker_stopped = False
    
    # Create new worker instance using configuration
    _worker_instance = ExtractionWorker(
        polling_interval=config.worker_polling_interval,
        max_concurrent_jobs=config.worker_max_concurrent_jobs
    )
    
    def run_worker():
        """Run the worker in the thread."""
        try:
            asyncio.run(_worker_instance.start())
        except KeyboardInterrupt:
            logger.info("Worker received keyboard interrupt")
        except Exception as e:
            logger.error(f"Worker crashed: {e}", exc_info=True)
    
    # Start worker in daemon thread
    _worker_thread = threading.Thread(target=run_worker, daemon=True)
    _worker_thread.start()
    
    logger.info("✅ Background worker started")
    return True

def stop_worker():
    """Stop the extraction worker."""
    global _worker_instance, _worker_stopped
    
    if _worker_instance and not _worker_stopped:
        logger.info("🛑 Stopping background worker...")
        _worker_instance.stop()
        _worker_stopped = True
        logger.info("✅ Background worker stopped")
    elif _worker_stopped:
        logger.debug("Worker already stopped, skipping")

def restart_worker() -> bool:
    """
    Restart the worker.
    
    Returns:
        True if worker was restarted successfully
    """
    logger.info("Restarting worker...")
    stop_worker()
    
    # Give it a moment to stop
    import time
    time.sleep(1)
    
    return start_worker()

def is_worker_running() -> bool:
    """Check if the worker is currently running."""
    global _worker_instance
    return _worker_instance is not None and _worker_instance.is_running

def get_worker_stats() -> dict:
    """Get worker statistics."""
    global _worker_instance
    
    if not _worker_instance:
        return {
            "status": "not_started",
            "message": "Worker not initialized"
        }
    
    try:
        # This would need to be called from an async context
        # For now, return basic info
        return {
            "status": "running" if _worker_instance.is_running else "stopped",
            "polling_interval": _worker_instance.polling_interval,
            "max_concurrent_jobs": _worker_instance.max_concurrent_jobs,
            "active_jobs": len(_worker_instance.active_jobs) if hasattr(_worker_instance, 'active_jobs') else 0
        }
    except Exception as e:
        logger.error(f"Error getting worker stats: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

# Register cleanup function to stop worker on exit
atexit.register(stop_worker)

# Auto-start worker when module is imported
def _auto_start_worker():
    """Auto-start the worker when the module is imported."""
    try:
        start_worker()
    except Exception as e:
        logger.error(f"Failed to auto-start worker: {e}")

# Start worker automatically
_auto_start_worker()
