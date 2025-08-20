"""
Core extraction engine for processing text documents.
Based on pulse implementation, adapted for pulse-application-layer.
"""

import json
import re
import logging
from typing import List, Dict, Any, Set, Tuple
from app.service.gemini import GeminiModel
from app.prompts.extraction import data_extraction_prompt, topic_normalization_prompt
from app.prompts.extraction import summarization_prompt

logger = logging.getLogger(__name__)

class Extraction:
    """
    Core extraction engine for processing text documents.
    Extracts entities, relationships, and generates summaries.
    """
    
    def __init__(self, model: GeminiModel, topics: Set[str] = None):
        """
        Initialize extraction engine.
        
        Args:
            model: Gemini AI model instance
            topics: Set of existing topics for normalization
        """
        self.model = model
        self.topics = topics or set()
        self.chunks = []
        
        logger.info("✅ Extraction engine initialized")
    
    def _chunk_text(self, text: str, chunk_size: int = 1000) -> List[str]:
        """
        Split text into manageable chunks for processing.
        
        Args:
            text: Text to chunk
            chunk_size: Maximum size of each chunk
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            if end >= text_length:
                chunks.append(text[start:].strip())
                break
            
            # Try to break at sentence boundaries
            period_pos = text.find('.', end)
            if period_pos != -1:
                end = period_pos + 1
            
            chunk = text[start:end].strip()
            chunks.append(chunk)
            start = end
        
        self.chunks = chunks
        logger.info(f"📝 Text chunked into {len(chunks)} chunks")
        return chunks
    
    def _extract_data_from_chunk(self, chunk: str, chunk_index: int) -> Dict[str, Any]:
        """
        Extract entities and relationships from a single text chunk.
        
        Args:
            chunk: Text chunk to process
            chunk_index: Index of the chunk
            
        Returns:
            Dictionary with entities and relationships
        """
        try:
            logger.info(f"🔄 Processing chunk {chunk_index + 1}/{len(self.chunks)}")
            
            # Get AI response
            response = self.model.get_response(
                prompt=data_extraction_prompt(chunk), 
                temperature=0.1
            )
            
            if not response.text:
                logger.warning(f"Empty response for chunk {chunk_index}")
                return {"entities": [], "relationships": []}
            
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response.text)
            if not json_match:
                logger.error(f"No JSON found in response for chunk {chunk_index}")
                return {"entities": [], "relationships": []}
            
            # Parse JSON
            data = json.loads(json_match.group(0))
            
            # Normalize topics in entities
            entities = self._normalize_topics(data.get("entities", []))
            relationships = data.get("relationships", [])
            
            logger.info(f"✅ Chunk {chunk_index + 1}: {len(entities)} entities, {len(relationships)} relationships")
            
            return {
                "entities": entities,
                "relationships": relationships
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing chunk {chunk_index}: {e}")
            return {"entities": [], "relationships": []}
    
    def _normalize_topics(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize topic names using AI model.
        
        Args:
            entities: List of entities with potential topics
            
        Returns:
            List of entities with normalized topics
        """
        normalized_entities = []
        
        for entity in entities:
            if entity.get("entity_type") == "Event" and entity.get("topic"):
                raw_topic = entity["topic"].strip().lower()
                
                try:
                    # Use AI to normalize topic
                    response = self.model.get_response(
                        prompt=topic_normalization_prompt(
                            topics=sorted(list(self.topics)), 
                            topic=raw_topic
                        ),
                        temperature=0.1
                    )
                    
                    if response.text:
                        # Extract normalized topic
                        json_match = re.search(r'\{[\s\S]*\}', response.text)
                        if json_match:
                            topic_data = json.loads(json_match.group(0))
                            normalized_topic = topic_data.get("topic", "").strip().lower()
                            
                            if normalized_topic:
                                entity["topic"] = normalized_topic
                                self.topics.add(normalized_topic)
                                logger.debug(f"Topic normalized: '{raw_topic}' -> '{normalized_topic}'")
                
                except Exception as e:
                    logger.warning(f"Failed to normalize topic '{raw_topic}': {e}")
                    # Keep original topic if normalization fails
                    self.topics.add(raw_topic)
            
            normalized_entities.append(entity)
        
        return normalized_entities
    
    def _generate_summary(self, text: str) -> Tuple[str, str]:
        """
        Generate title and summary for the document.
        
        Args:
            text: Full text to summarize
            
        Returns:
            Tuple of (title, summary)
        """
        try:
            logger.info("📝 Generating document summary...")
            
            # Generate summary
            summary_response = self.model.get_response(
                prompt=summarization_prompt(text, focus="meeting or conversation"),
                temperature=0.3
            )
            
            if not summary_response.text:
                logger.warning("Empty summary response")
                return "Document Summary", "No summary generated"
            
            # Try to extract title and summary
            summary_text = summary_response.text.strip()
            
            # Simple heuristic: first line as title, rest as summary
            lines = summary_text.split('\n')
            title = lines[0].strip() if lines else "Document Summary"
            summary = '\n'.join(lines[1:]).strip() if len(lines) > 1 else summary_text
            
            # Clean up title (remove common prefixes)
            title = re.sub(r'^(Title|Summary|Document):\s*', '', title, flags=re.IGNORECASE)
            
            logger.info(f"✅ Summary generated: '{title[:50]}...'")
            return title, summary
            
        except Exception as e:
            logger.error(f"❌ Error generating summary: {e}")
            return "Document Summary", "Error generating summary"
    
    def process_document(self, text: str) -> Dict[str, Any]:
        """
        Process a complete document and extract structured information.
        
        Args:
            text: Document text to process
            
        Returns:
            Dictionary with extracted information
        """
        logger.info("🚀 Starting document processing...")
        
        # Chunk the text
        chunks = self._chunk_text(text)
        
        # Process each chunk
        all_entities = []
        all_relationships = []
        
        for i, chunk in enumerate(chunks):
            result = self._extract_data_from_chunk(chunk, i)
            all_entities.extend(result.get("entities", []))
            all_relationships.extend(result.get("relationships", []))
        
        # Generate document summary
        title, summary = self._generate_summary(text)
        
        # Prepare metadata
        metadata = {
            "total_chunks": len(chunks),
            "total_entities": len(all_entities),
            "total_relationships": len(all_relationships),
            "entity_types": list(set(e.get("entity_type") for e in all_entities)),
            "topics": list(self.topics),
            "processing_stats": {
                "chunk_size": 1000,
                "model_used": self.model.model_name
            }
        }
        
        logger.info(f"✅ Document processing completed: {len(all_entities)} entities, {len(all_relationships)} relationships")
        
        return {
            "title": title,
            "summary": summary,
            "entities": all_entities,
            "relationships": all_relationships,
            "metadata": metadata,
            "topics": list(self.topics)
        }
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return {
            "total_chunks": len(self.chunks),
            "total_topics": len(self.topics),
            "model_name": self.model.model_name
        }
