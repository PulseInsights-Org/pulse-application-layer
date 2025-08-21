"""
Core extraction engine for processing text documents.
Based on pulse implementation, adapted for pulse-application-layer.
"""

import json
import re
import logging
from typing import List, Dict, Any, Set, Tuple, Optional, Union
from app.service.gemini import GeminiModel
from app.prompts.extraction import data_extraction_prompt, topic_normalization_prompt
from app.prompts.extraction import summarization_prompt

# Optional imports for database integrations
try:
    from app.core.graph import GraphBuilder
except ImportError:
    GraphBuilder = None

try:
    from app.service.vector import PineconeStore
except ImportError:
    PineconeStore = None

logger = logging.getLogger(__name__)

def extract_json_string(model_output: str) -> str:
    """Extract JSON object from model output."""
    m = re.search(r'\{[\s\S]*\}', model_output)
    if not m:
        raise ValueError("No JSON object found in model output")
    return m.group(0)

class Extraction:
    """
    Core extraction engine for processing text documents.
    Extracts entities, relationships, and generates summaries.
    """
    
    def __init__(self, model: GeminiModel, pinecone: Optional[Any] = None, graph: Optional[Any] = None, topics: Set[str] = None):
        """
        Initialize extraction engine with database connections.
        
        Args:
            model: Gemini AI model instance
            pinecone: Pinecone vector store instance
            graph: Neo4j graph builder instance
            topics: Set of existing topics for normalization
        """
        self.model = model
        self.pc = pinecone
        self.builder = graph
        self.topics = topics or set()
        self.chunks = []
        
        # Initialize databases if provided
        if self.builder:
            self.builder._initialize_graph()
            logger.info("✅ Neo4j graph database initialized")
        
        if self.pc:
            self.pc.setup_indexes()
            logger.info("✅ Pinecone vector database initialized")
        
        if pinecone and graph:
            logger.info("✅ Extraction engine initialized with full database connections")
        elif pinecone or graph:
            logger.info("✅ Extraction engine initialized with partial database connections")
        else:
            logger.info("✅ Extraction engine initialized (memory-only mode)")
    
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
        Extract entities and relationships from a single text chunk and save to databases.
        
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
            
            # Get entities and relationships
            entities = data.get("entities", [])
            relationships = data.get("relationships", [])
            
            # Normalize topics in entities
            entities = self._normalize_topics(entities)
            
            # Filter relationships (remove self-references and topic-only relationships)
            topic_names = {
                (e.get("entity_name") or "").strip().lower()
                for e in entities
                if (e.get("entity_type") or "").strip().lower() == "topic"
            }

            relationships = [
                r for r in relationships
                if not (
                    r.get("relationship_type", "").strip().upper() == "RELATED_TO"
                    and (
                        (r.get("target_entity") or "").strip().lower() in topic_names
                        or ((r.get("source_entity") or "").strip().lower()
                            == (r.get("target_entity") or "").strip().lower())
                    )
                )
            ]
            
            # Save to Neo4j if available
            to_split = False
            topic_value = []
            
            if self.builder:
                try:
                    to_split, topic_value = self.builder._add_nodes(entities)
                    self.builder._add_edges(relationships)
                    
                    # Handle topic splitting if needed
                    if to_split:
                        logger.info(f"Event count on topic exceeded threshold, splitting topics...")
                        for topic in topic_value:
                            self._split_topics(topic)
                except Exception as e:
                    logger.warning(f"Failed to save to Neo4j: {e}")
            else:
                logger.info("Skipping Neo4j storage (graph database not configured)")
            
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
    
    def _split_topics(self, topic_name: str):
        """
        Split topics when they have too many events.
        
        Args:
            topic_name: Name of topic to split
        """
        if not self.builder:
            logger.info(f"Topic splitting skipped (Neo4j not configured): {topic_name}")
            return
            
        try:
            # Get events for this topic
            result = self.builder._run("""
                MATCH (ev:Event)-[:ABOUT]->(tp:Topic {name: $topic_name})
                RETURN ev.name AS event_name
            """, topic_name=topic_name)
            events = [row["event_name"] for row in result]
            
            # Use AI to split topics (would need split_topics prompt)
            # For now, just log that splitting would happen
            logger.info(f"Would split topic '{topic_name}' with {len(events)} events")
            
        except Exception as e:
            logger.error(f"Error splitting topic '{topic_name}': {e}")
    
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
    
    def _get_topic_summary(self):
        """Generate summaries for topics and store in Pinecone."""
        try:
            # Get all topics
            topics_query = """
                MATCH (t:Topic)
                RETURN t.name AS topic_name
            """
            topics = list(self.builder._run(topics_query))
            
            for topic in topics:
                topic_name = topic["topic_name"]
                
                # Get topic details
                per_topic_query = """
                    MATCH (t:Topic {name: $topic})
                    OPTIONAL MATCH (t)<-[:ABOUT]-(e:Event)-[r]-(n)
                    WHERE r IS NOT NULL
                    RETURN
                        t.summary AS summary,
                        collect(DISTINCT {event_name: e.name, description: e.description}) AS events,
                        collect(DISTINCT coalesce(r.description, type(r))) AS relationship_descriptions
                """
                
                rows = list(self.builder._run(per_topic_query, topic=topic_name))
                if not rows:
                    continue
                    
                row = rows[0]
                existing_summary = row.get("summary")
                events = row.get("events", []) or []
                relationships = row.get("relationship_descriptions", []) or []
                
                # Generate topic summary
                event_text = "\n".join([
                    f"Event: {e.get('event_name','(unknown)')} - {e.get('description','')}".strip()
                    for e in events
                ])
                
                relationship_text = "\n\n".join(desc.strip() for desc in relationships if desc)
                
                # Use summarization prompt for topic
                summary_prompt = f"""
                Generate a concise summary for the topic "{topic_name}" based on the following information:

                Events:
                {event_text}

                Relationships:
                {relationship_text}

                {"Build upon this existing summary: " + existing_summary if existing_summary else ""}

                Format as JSON:
                {{
                    "summary": "your summary here",
                    "findings": [
                        {{
                            "main_event": "key event",
                            "sub_events": ["supporting events"],
                            "summary": "event summary"
                        }}
                    ]
                }}
                """
                
                response = self.model.get_response(prompt=summary_prompt, temperature=0.0)
                response_text = response.text if hasattr(response, "text") else str(response)
                
                try:
                    clean_json = extract_json_string(response_text)
                    parsed = json.loads(clean_json)
                    parsed["title"] = topic_name
                    
                    # Update Neo4j with summary
                    metadata_str = json.dumps(parsed, ensure_ascii=False)
                    update_cypher = """
                    MATCH (t:Topic {name: $topic})
                    SET t.summary = $summary,
                        t.metadata = $metadata
                    """
                    self.builder._run(
                        update_cypher,
                        topic=topic_name,
                        summary=parsed.get("summary", ""),
                        metadata=metadata_str
                    )
                    
                    # Get topic node ID for Pinecone
                    id_query = """
                    MATCH (n:Topic {name: $topic_name})
                    RETURN elementId(n) AS id
                    """
                    id_result = self.builder._run(id_query, topic_name=topic_name)
                    
                    if id_result:
                        topic_id = id_result[0]["id"]
                        parsed["id"] = topic_id
                        
                        # Store in Pinecone
                        response = self.pc.add_main_events(metadata=parsed)
                        logger.info(f"✅ Added topic '{topic_name}' to Pinecone: {response}")
                    
                    logger.info(f"✅ Updated topic '{topic_name}' with summary and metadata")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse topic summary JSON: {e}")
                    
        except Exception as e:
            logger.error(f"Error generating topic summaries: {e}")
    
    def process_document(self, text: str) -> Dict[str, Any]:
        """
        Process a complete document and extract structured information.
        Saves data to Neo4j and Pinecone databases.
        
        Args:
            text: Document text to process
            
        Returns:
            Dictionary with extracted information
        """
        logger.info("🚀 Starting document processing with database integration...")
        
        # Chunk the text
        chunks = self._chunk_text(text)
        
        # Process each chunk and save to databases
        all_entities = []
        all_relationships = []
        
        for i, chunk in enumerate(chunks):
            result = self._extract_data_from_chunk(chunk, i)
            all_entities.extend(result.get("entities", []))
            all_relationships.extend(result.get("relationships", []))
        
        # Generate document summary
        title, summary = self._generate_summary(text)
        
        # Generate topic summaries and store in Pinecone (if available)
        if self.pc:
            logger.info("📝 Generating topic summaries...")
            self._get_topic_summary()
        else:
            logger.info("📝 Skipping topic summaries (Pinecone not configured)")
        
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
            },
            "database_integration": {
                "neo4j_enabled": self.builder is not None,
                "pinecone_enabled": self.pc is not None
            }
        }
        
        logger.info(f"✅ Document processing completed: {len(all_entities)} entities, {len(all_relationships)} relationships saved to databases")
        
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
            "model_name": self.model.model_name,
            "neo4j_connected": self.builder is not None,
            "pinecone_connected": self.pc is not None
        }
