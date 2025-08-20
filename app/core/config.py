"""
Configuration management for the ingestion pipeline.
Loads tenant-specific secrets from Supabase tenant_secrets table.
Based on pulse implementation.
"""

import os
import time
from typing import Dict, Any, Optional
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Cache for tenant secrets
_secrets_cache = {}  # {tenant_id: (secrets, expiry)}
SECRETS_CACHE_TTL = 12 * 3600  # 12 hours

class Config:
    """Configuration class for the ingestion pipeline."""
    
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.secrets: Dict[str, Any] = {}
        self.tenant_id: Optional[str] = None
        
        # Don't load secrets here - they'll be loaded per-request based on org_id
        
    def _get_supabase_client(self) -> Client:
        """Get or create Supabase client."""
        return create_client(self.supabase_url, self.supabase_key)
    
    def _resolve_tenant_from_org(self, org_id: str) -> str:
        """
        Resolve tenant_id from org_id using org_directory table.
        
        Args:
            org_id: Organization ID from header
            
        Returns:
            tenant_id for the organization
        """
        try:
            client = self._get_supabase_client()
            resp = client.table("org_directory").select("tenant_id,status").eq("org_id", org_id).single().execute()
            
            row = resp.data
            if not row or row.get("status") != "active":
                raise ValueError(f"Org {org_id} not found or inactive")
            
            return row["tenant_id"]
            
        except Exception as e:
            logger.error(f"Failed to resolve tenant for org {org_id}: {e}")
            raise ValueError(f"Tenant resolution failed: {e}")
    
    def load_tenant_secrets(self, org_id: str) -> bool:
        """
        Load tenant-specific secrets for the given org_id.
        
        Args:
            org_id: Organization ID from request header
            
        Returns:
            True if secrets loaded successfully
        """
        try:
            # Resolve tenant_id from org_id
            tenant_id = self._resolve_tenant_from_org(org_id)
            self.tenant_id = tenant_id
            
            # Check cache first
            cached = _secrets_cache.get(tenant_id)
            if cached and cached[1] > time.time():
                self.secrets = cached[0]
                logger.info(f"✅ Loaded {len(self.secrets)} secrets from cache for tenant {tenant_id}")
                return True
            
            # Load from database
            client = self._get_supabase_client()
            result = client.table("tenant_secrets").select("*").eq("tenant_id", tenant_id).single().execute()
            
            if result.data:
                self.secrets = result.data
                # Cache the result
                _secrets_cache[tenant_id] = (self.secrets, time.time() + SECRETS_CACHE_TTL)
                logger.info(f"✅ Loaded {len(self.secrets)} secrets from database for tenant {tenant_id}")
                return True
            else:
                logger.error(f"No secrets found for tenant {tenant_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error loading tenant secrets for org {org_id}: {e}")
            # Fallback to environment variables for critical secrets
            self.secrets = {
                "model_name": os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash"),
                "model_api_key": os.getenv("GEMINI_API_KEY"),
                "pinecone_api_key": os.getenv("PINECONE_API_KEY"),
                "pinecone_index": os.getenv("PINECONE_INDEX"),
                "neo4j_uri": os.getenv("NEO4J_URI"),
                "neo4j_user": os.getenv("NEO4J_USER"),
                "neo4j_password": os.getenv("NEO4J_PASSWORD"),
                "neo4j_database": os.getenv("NEO4J_DATABASE"),
            }
            logger.warning("Using fallback environment variables for secrets")
            return False
    
    def get_secret(self, key: str, default: Any = None) -> Any:
        """Get a secret value by key."""
        return self.secrets.get(key, default)
    
    def get_gemini_config(self) -> Dict[str, str]:
        """Get Gemini AI configuration."""
        return {
            "api_key": self.get_secret("model_api_key"),
            "model_name": self.get_secret("model_name", "gemini-1.5-flash")
        }
    
    def get_pinecone_config(self) -> Dict[str, str]:
        """Get Pinecone vector database configuration."""
        return {
            "api_key": self.get_secret("pinecone_api_key"),
            "index_name": self.get_secret("pinecone_index")
        }
    
    def get_neo4j_config(self) -> Dict[str, str]:
        """Get Neo4j graph database configuration."""
        return {
            "uri": self.get_secret("neo4j_uri"),
            "user": self.get_secret("neo4j_user"),
            "password": self.get_secret("neo4j_password"),
            "database": self.get_secret("neo4j_database")
        }
    
    def has_tenant_secrets(self) -> bool:
        """Check if tenant secrets are loaded."""
        return bool(self.secrets and self.tenant_id)
    
    def clear_cache(self, tenant_id: str = None):
        """Clear secrets cache."""
        if tenant_id:
            _secrets_cache.pop(tenant_id, None)
        else:
            _secrets_cache.clear()

# Global config instance
config = Config()
