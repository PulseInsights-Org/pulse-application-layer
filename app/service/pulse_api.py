"""
HTTP client service for calling the pulse project's extraction API.
Handles authentication, content upload, and response processing.
"""

import httpx
import logging
import json
from typing import Dict, Any, Optional
from app.core.config import Config

logger = logging.getLogger(__name__)

class PulseAPIClient:
    """Client for calling the pulse project's extraction API."""
    
    def __init__(self, base_url: str, org_name: str):
        """
        Initialize the pulse API client.
        
        Args:
            base_url: Base URL of the pulse API (e.g., "http://localhost:8000")
            org_id: Organization ID for tenant isolation
        """
        self.base_url = base_url.rstrip('/')
        self.config = Config()
        self.org_name = org_name
        
        org_resp = (
            self.config._get_supabase_client()
            .table("orgs")
            .select("id")
            .eq("org_name", org_name)
            .execute()
        )

        from fastapi import HTTPException
        if not org_resp.data:
            raise HTTPException(status_code=404, detail="Organization not found")

        self.org_id = org_resp.data[0]["id"] 
        
        
        # Create HTTP client with timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0),  # 5 minutes for extraction
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        logger.info(f"✅ Pulse API client initialized for org {org_name} at {base_url}")
    
    async def extract_content(self, content: str, filename: str = "document.txt", intake_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Send content to the pulse extraction API for processing.
        
        Args:
            content: Text content to extract
            filename: Filename for the content (used by the API)
            intake_id: The intake ID to track this extraction job
            
        Returns:
            Extraction result dictionary if successful, None otherwise
        """
        files = {"file": (filename, content.encode('utf-8'), "text/plain")}
        headers = {"x-org-name": self.org_name}

        # Add intake ID header if provided
        if intake_id:
            headers["x-intake-id"] = intake_id

        url = f"{self.base_url}/api/v1/ingestion/"

        logger.info(f"🔄 Sending content to pulse API: {url}")
        logger.info(f"Content length: {len(content)} characters")
        if intake_id:
            logger.info(f"📋 Intake ID: {intake_id}")

        try:
            # Up to 3 attempts, retrying only on JSON parsing error
            for attempt in range(1, 4):
                response = await self.client.post(url, files=files, headers=headers)

                if response.status_code in (200, 202):
                    try:
                        result = response.json()
                        logger.info(
                            f"✅ Extraction API call successful (status {response.status_code}): {result.get('message', 'No message')}"
                        )
                        return result
                    except json.JSONDecodeError as je:
                        snippet = response.text[:500] if response.text else ""
                        if attempt < 3:
                            logger.error(
                                f"❌ Failed to parse extraction API response JSON (attempt {attempt}/3): {je}. Body snippet: {snippet}. Retrying..."
                            )
                            continue
                        else:
                            logger.error(
                                f"❌ Failed to parse extraction API response JSON after 3 attempts: {je}. Body snippet: {snippet}"
                            )
                            return None

                # Non-success status: do not add complexity; keep prior behavior
                logger.error(
                    f"❌ Extraction API call failed: {response.status_code} - {response.text}"
                )
                return None

            return None

        except httpx.TimeoutException:
            logger.error("❌ Extraction API call timed out")
            return None
        except httpx.RequestError as e:
            logger.error(f"❌ Extraction API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error calling extraction API: {e}")
            return None
    
    async def get_api_status(self) -> Optional[Dict[str, Any]]:
        """
        Check the status of the pulse API.
        
        Returns:
            API status information if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/api/v1/ingestion/status"
            headers = {"x-org-id": self.org_id}
            response = await self.client.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"API status check failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error checking API status: {e}")
            return None
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("Pulse API client closed")
    
    def __del__(self):
        """Cleanup when the object is destroyed."""
        try:
            # Try to close the client if it's still open
            if hasattr(self, 'client') and not self.client.is_closed:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self.client.aclose())
                except RuntimeError:
                    # No event loop, client will be cleaned up by garbage collection
                    pass
        except Exception:
            pass