"""
Pinecone vector database integration for storing document embeddings.
Based on pulse implementation.
"""

from pinecone import Pinecone
import uuid
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class PineconeStore:
    """Pinecone vector database store for document embeddings."""
    
    def __init__(self, api_key: str, index_name: str = "main-events-index"):
        """
        Initialize Pinecone connection.
        
        Args:
            api_key: Pinecone API key
            index_name: Index name for storing vectors
        """
        self.pc = Pinecone(api_key=api_key)
        # Sanitize index name: convert underscores to hyphens, ensure lowercase
        self.index_name = index_name.lower().replace("_", "-")
        self.index = None
        logger.info(f"✅ PineconeStore initialized: {self.index_name} (sanitized from: {index_name})")
    
    def setup_indexes(self):
        """Set up Pinecone indexes if they don't exist."""
        try:
            if not self.pc.has_index(self.index_name):
                logger.info(f"Creating Pinecone index: {self.index_name}")
                self.pc.create_index_for_model(
                    name=self.index_name,
                    cloud="aws",
                    region="us-east-1",
                    embed={
                        "model": "llama-text-embed-v2",
                        "field_map": {"text": "text"}
                    }
                )
                logger.info(f"✅ Created Pinecone index: {self.index_name}")
            else:
                logger.info(f"✅ Pinecone index already exists: {self.index_name}")
                
            self.index = self.pc.Index(self.index_name)
            
        except Exception as e:
            logger.error(f"Error setting up Pinecone index: {e}")
            # Create a mock index for testing
            self.index = None
    
    def _create_text_for_embedding(self, finding: Dict[str, Any]) -> str:
        """
        Create text for embedding from finding data.
        
        Args:
            finding: Finding dictionary with main_event, sub_events, summary
            
        Returns:
            Combined text for embedding
        """
        main_event = finding.get("main_event", "")
        sub_events = finding.get("sub_events", [])
        summary = finding.get("summary", "")
        
        sub_events_text = " ".join(sub_events) if sub_events else ""
        combined_text = f"{main_event} {sub_events_text} {summary}".strip()
        return combined_text
    
    def add_main_events(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add main events to Pinecone vector store.
        
        Args:
            metadata: Metadata dictionary with findings, title, etc.
            
        Returns:
            Dictionary with operation status
        """
        try:
            if not self.index:
                logger.warning("Pinecone index not available, skipping vector storage")
                return {
                    "status": "skipped",
                    "message": "Pinecone index not available"
                }
            
            findings = metadata.get("findings", [])
            title = metadata.get("title", "")
            node_id = metadata.get("id", None)
            
            if not findings:
                logger.warning("No findings found in metadata")
                return {
                    "status": "error",
                    "message": "No findings found in metadata"
                }
            
            records = []
            
            logger.info(f"Creating vectors for {len(findings)} findings")
            for finding in findings:
                text_for_embedding = self._create_text_for_embedding(finding)
                vector_id = str(uuid.uuid4())
                
                records.append({
                    "_id": vector_id,
                    "text": text_for_embedding,
                    "title": title,
                    "node_id": node_id,
                    "main_event": finding.get("main_event", ""),
                    "sub_events": finding.get("sub_events", []),
                    "summary": finding.get("summary", ""),
                    "created_at": "2025-01-01T00:00:00Z"
                })
            
            # Upsert to Pinecone
            upsert_response = self.index.upsert_records(
                self.index_name,
                records
            )
            logger.info(f"✅ Upsert response: {upsert_response}")
            
            return {
                "status": "success",
                "message": f"Added {len(records)} main events",
                "upserted_count": len(records),
                "title": title,
                "node_id": node_id
            }
            
        except Exception as e:
            logger.error(f"Error adding main events to Pinecone: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def delete_main_events(self, node_id: str) -> Dict[str, Any]:
        """
        Delete main events from Pinecone vector store.
        
        Args:
            node_id: Node ID to delete vectors for
            
        Returns:
            Dictionary with operation status
        """
        try:
            if not self.index:
                logger.warning("Pinecone index not available, skipping vector deletion")
                return {
                    "status": "skipped",
                    "message": "Pinecone index not available"
                }
            
            # Query for vectors with this node_id
            query_response = self.index.query(
                filter={"node_id": node_id},
                top_k=1000,  # Adjust as needed
                include_metadata=True
            )
            
            if query_response.matches:
                vector_ids = [match.id for match in query_response.matches]
                
                # Delete the vectors
                delete_response = self.index.delete(ids=vector_ids)
                logger.info(f"✅ Deleted {len(vector_ids)} vectors for node {node_id}")
                
                return {
                    "status": "success",
                    "message": f"Deleted {len(vector_ids)} vectors",
                    "deleted_count": len(vector_ids),
                    "node_id": node_id
                }
            else:
                return {
                    "status": "success",
                    "message": "No vectors found to delete",
                    "deleted_count": 0,
                    "node_id": node_id
                }
                
        except Exception as e:
            logger.error(f"Error deleting main events from Pinecone: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def search_similar(self, query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Pinecone.
        
        Args:
            query_text: Text to search for
            top_k: Number of results to return
            
        Returns:
            List of similar documents
        """
        try:
            if not self.index:
                logger.warning("Pinecone index not available, returning empty results")
                return []
            
            # This would normally use embeddings, but for now return empty
            # In a full implementation, you'd generate embeddings for query_text
            # and search using self.index.query()
            
            return []
            
        except Exception as e:
            logger.error(f"Error searching Pinecone: {str(e)}")
            return []
