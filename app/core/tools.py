from app.service.vector_store import PineconeStore
import re
from app.service.graph_store import Neo4jDriver
from typing import List

class GeminiTools():
    
    def __init__(self, secrets):
        
        self.builder = Neo4jDriver(
            uri=secrets["neo4j_uri"],
            user=secrets["neo4j_user"],
            password=secrets["neo4j_password"])
        
        s = secrets["pinecone_index"]
        s = s.strip().lower()
        s = re.sub(r'[^a-z0-9-]+', '-', s)    
        s = re.sub(r'-{2,}', '-', s)           
        s = s.strip('-')                        
        if not s:
            s = "default"
        s= s[:15]
        
        self.pc = PineconeStore(
            api_key=secrets["pinecone_api_key"],
            index_name=s
        )
        self.pc.setup_indexes()
    
    def get_event_connections(self, event_names: List[str]):
    
        cypher = """
        UNWIND $names AS event_name
        MATCH (e:Event {name: event_name})-[r]-(n)
        RETURN event_name AS event,
            n.name AS related_node,
            labels(n)[0] AS node_type,
            type(r) AS relationship_type,
            r.description AS relationship_description
        ORDER BY event_name, related_node
        """
        return self.builder._run(cypher, names=[e for e in event_names])
    
    def pc_retrieval_tool(self, query):
        
        print("fetching from Pinecone")
        results = self.pc.search_main_events(query_text=query)
        return results["results"]
