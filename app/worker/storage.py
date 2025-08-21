"""
Storage operations for the extraction worker.
Handles downloading files from Supabase Storage and checksum verification.
"""

import hashlib
import logging
from typing import Optional, Tuple
from supabase import Client

logger = logging.getLogger(__name__)

class WorkerStorage:
    """Storage operations for the extraction worker."""
    
    def __init__(self, supabase_client: Client):
        """
        Initialize worker storage operations.
        
        Args:
            supabase_client: Supabase client instance
        """
        self.client = supabase_client
        self.bucket_name = "intakes-raw"
    
    async def download_intake_content(self, storage_path: str) -> Optional[str]:
        """
        Download the content of an intake from storage.
        
        Args:
            storage_path: Storage path for the intake (e.g., "org/org1/intake/123/")
            
        Returns:
            File content as string if successful, None otherwise
        """
        try:
            # Remove trailing slash for proper path handling
            path_for_listing = storage_path.rstrip('/')
            
            # List files in the intake directory
            files_result = self.client.storage.from_(self.bucket_name).list(path_for_listing)
            
            if not files_result or len(files_result) == 0:
                logger.error(f"No files found in storage path: {storage_path}")
                return None
            
            # Get the first file (assuming one file per intake for MVP)
            file_info = files_result[0]
            file_path = f"{path_for_listing}/{file_info['name']}"
            
            logger.info(f"Downloading file: {file_path}")
            
            # Download file content
            file_content = self.client.storage.from_(self.bucket_name).download(file_path)
            
            if file_content:
                # Convert bytes to string if needed
                if isinstance(file_content, bytes):
                    content_str = file_content.decode('utf-8')
                else:
                    content_str = str(file_content)
                
                logger.info(f"Successfully downloaded {len(content_str)} characters from {file_path}")
                return content_str
            else:
                logger.error(f"Empty content downloaded from {file_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading content from {storage_path}: {e}")
            return None
    
    async def verify_checksum(self, content: str, expected_checksum: str) -> bool:
        """
        Verify the checksum of downloaded content.
        
        Args:
            content: Content to verify
            expected_checksum: Expected MD5 checksum
            
        Returns:
            True if checksum matches, False otherwise
        """
        try:
            # Calculate MD5 checksum of content
            if isinstance(content, str):
                content_bytes = content.encode('utf-8')
            else:
                content_bytes = content
            
            calculated_checksum = hashlib.md5(content_bytes).hexdigest()
            
            if calculated_checksum == expected_checksum:
                logger.debug(f"Checksum verification passed: {calculated_checksum}")
                return True
            else:
                logger.error(f"Checksum mismatch. Expected: {expected_checksum}, Calculated: {calculated_checksum}")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying checksum: {e}")
            return False
    
    async def download_and_verify(self, storage_path: str, expected_checksum: str) -> Optional[str]:
        """
        Download content and verify its checksum in one operation.
        
        Args:
            storage_path: Storage path for the intake
            expected_checksum: Expected MD5 checksum
            
        Returns:
            File content if download and verification successful, None otherwise
        """
        try:
            # Download content
            content = await self.download_intake_content(storage_path)
            
            if content is None:
                return None
            
            # Verify checksum
            if not await self.verify_checksum(content, expected_checksum):
                logger.error(f"Checksum verification failed for {storage_path}")
                return None
            
            logger.info(f"Successfully downloaded and verified content from {storage_path}")
            return content
            
        except Exception as e:
            logger.error(f"Error in download and verify for {storage_path}: {e}")
            return None
    
    async def get_file_info(self, storage_path: str) -> Optional[Tuple[str, int]]:
        """
        Get information about the file in the storage path.
        
        Args:
            storage_path: Storage path for the intake
            
        Returns:
            Tuple of (filename, size) if found, None otherwise
        """
        try:
            # Remove trailing slash for proper path handling
            path_for_listing = storage_path.rstrip('/')
            
            # List files in the intake directory
            files_result = self.client.storage.from_(self.bucket_name).list(path_for_listing)
            
            if not files_result or len(files_result) == 0:
                logger.warning(f"No files found in storage path: {storage_path}")
                return None
            
            # Get the first file info
            file_info = files_result[0]
            filename = file_info.get('name', 'unknown')
            file_size = file_info.get('metadata', {}).get('size', 0)
            
            return filename, file_size
            
        except Exception as e:
            logger.error(f"Error getting file info for {storage_path}: {e}")
            return None
    
    async def list_intake_files(self, storage_path: str) -> Optional[list]:
        """
        List all files in an intake storage path.
        
        Args:
            storage_path: Storage path for the intake
            
        Returns:
            List of file information dictionaries, None if error
        """
        try:
            # Remove trailing slash for proper path handling
            path_for_listing = storage_path.rstrip('/')
            
            # List files in the intake directory
            files_result = self.client.storage.from_(self.bucket_name).list(path_for_listing)
            
            if files_result:
                logger.debug(f"Found {len(files_result)} files in {storage_path}")
                return files_result
            else:
                logger.warning(f"No files found in storage path: {storage_path}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing files in {storage_path}: {e}")
            return None
