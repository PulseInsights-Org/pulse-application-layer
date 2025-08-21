"""
Neo4j graph database integration for storing entities and relationships.
Based on pulse implementation.
"""

from neo4j import GraphDatabase
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class GraphBuilder:
    """Neo4j graph database builder for storing extracted entities and relationships."""
    
    def __init__(self, uri: str, user: str, password: str, database: Optional[str] = "neo4j"):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Neo4j connection URI
            user: Neo4j username
            password: Neo4j password
            database: Neo4j database name
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.entity_index = {}
        logger.info(f"✅ GraphBuilder initialized: {uri}")

    def _run(self, cypher: str, **params):
        """
        Execute Cypher query.
        
        Args:
            cypher: Cypher query string
            **params: Query parameters
            
        Returns:
            List of query results
        """
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher, **params)
            return [dict(record) for record in result]
        
    def _initialize_graph(self):
        """Initialize graph database with required constraints and indexes."""
        logger.info("🔧 Initializing graph database...")
        
        # Create constraints
        constraints = [
            "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT event_name_unique IF NOT EXISTS FOR (n:Event) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT actor_name_unique IF NOT EXISTS FOR (n:Actor) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT time_name_unique IF NOT EXISTS FOR (n:Time) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.name IS UNIQUE"
        ]
        
        for constraint in constraints:
            try:
                self._run(constraint)
            except Exception as e:
                # Constraint might already exist, ignore
                pass
        
        # Create indexes
        indexes = [
            "CREATE INDEX topic_event_count_index IF NOT EXISTS FOR (n:Topic) ON (n.event_count)"
        ]
        
        for index in indexes:
            try:
                self._run(index)
            except Exception as e:
                # Index might already exist, ignore
                pass
        
        logger.info("✅ Graph database initialized")
        
    def _add_nodes(self, entities: List[Dict]) -> tuple:
        """
        Add entities as nodes to the graph.
        
        Args:
            entities: List of entity dictionaries
            
        Returns:
            Tuple of (exceeded_topics_flag, list_of_exceeded_topics)
        """
        exceeded_topics = []
        
        for entity in entities:
            name = entity.get("entity_name", "").lower().strip()
            etype = (entity.get("entity_type") or "").strip().title()
            desc = entity.get("entity_description", "")
            
            if not name or not etype:
                logger.warning(f"Skipping entity with missing name or type: {entity}")
                continue
            
            # Store in entity index for relationship validation
            if etype == "Event":
                topic = entity.get("topic", "").lower().strip()
                self.entity_index[name] = {"type": etype, "description": desc, "topic": topic}
            else:
                self.entity_index[name] = {"type": etype, "description": desc}
            
            # Create node in Neo4j
            cypher = f"""
            MERGE (n:{etype} {{name: $name}})
            ON CREATE SET n.description = $desc
            ON MATCH SET  n.description = coalesce(n.description, $desc)
            """
            self._run(cypher, name=name, desc=desc)
            
            # Handle Event-Topic relationships
            if etype == "Event" and entity.get("topic"):
                topic = entity.get("topic").lower().strip()
                
                # Create Topic node and relationship
                self._run("""
                    MERGE (tp:Topic {name: $topic})
                    ON CREATE SET tp.event_count = 0
                """, topic=topic)
                
                # Link Event to Topic
                self._run("""
                    MATCH (ev:Event {name: $event}), (tp:Topic {name: $topic})
                    MERGE (ev)-[:ABOUT]->(tp)
                    SET tp.event_count = coalesce(tp.event_count, 0) + 1
                """, event=name, topic=topic)
                
                # Check if topic has too many events (for splitting logic)
                result = self._run("""
                    MATCH (tp:Topic {name: $topic})
                    RETURN tp.event_count AS count
                """, topic=topic)
                
                if result and result[0].get("count", 0) > 50:  # Configurable threshold
                    exceeded_topics.append(topic)
        
        logger.info(f"✅ Added {len(entities)} entities to graph")
        return len(exceeded_topics) > 0, exceeded_topics
    
    def _add_edges(self, relationships: List[Dict]):
        """
        Add relationships as edges to the graph.
        
        Args:
            relationships: List of relationship dictionaries
        """
        rel_type_map = {
            "PERFORMED": "PERFORMED",
            "DISCUSSING": "DISCUSSING", 
            "OCCURRED_AT": "AT_TIME",
            "RELATED_TO": "RELATED_TO"
        }
        
        for r in relationships:
            src = r.get("source_entity", "").lower().strip()
            tgt = r.get("target_entity", "").lower().strip()
            desc = r.get("relationship_description", "")
            rel_type = r.get("relationship_type", "").strip().upper()
            
            if not src or not tgt:
                logger.warning(f"Skipping relationship with empty source or target: {r}")
                continue
            
            src_meta = self.entity_index.get(src)
            tgt_meta = self.entity_index.get(tgt)
            
            if not src_meta or not tgt_meta:
                logger.warning(f"Skipping relationship - entity not found: src='{src}' (found: {src_meta is not None}), tgt='{tgt}' (found: {tgt_meta is not None})")
                continue
            
            s_type = src_meta["type"]
            t_type = tgt_meta["type"]
            neo_rel_type = rel_type_map.get(rel_type)

            if not neo_rel_type:
                logger.warning(f"Skipping relationship with unmapped type: {rel_type}")
                continue

            try:
                cypher = f"""
                MATCH (a:{s_type} {{name: $src}}), (b:{t_type} {{name: $tgt}})
                MERGE (a)-[r:{neo_rel_type}]->(b)
                ON CREATE SET r.description = $desc
                ON MATCH SET  r.description = coalesce(r.description, $desc)
                """
                self._run(cypher, src=src, tgt=tgt, desc=desc)
            except Exception as e:
                logger.error(f"Error creating relationship {src} -> {tgt}: {e}")
                continue
        
        logger.info(f"✅ Added {len(relationships)} relationships to graph")
    
    def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            self.driver.close()
            logger.info("✅ Neo4j connection closed")
