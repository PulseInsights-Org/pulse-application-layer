import os
import time
from typing import Dict, Any, Optional
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

_secrets_cache = {}  # {id: (secrets, expiry)}
SECRETS_CACHE_TTL = 12 * 3600  # 12 hours

class Config:
    """Configuration class for the ingestion pipeline."""
    
    def __init__(self):
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        # Org ID for default tenant
        self.default_org_id = os.getenv("DEFAULT_ORG_ID")
        
        # Worker configuration from environment variables
        self.worker_polling_interval = int(os.getenv("WORKER_POLLING_INTERVAL", "30"))
        self.worker_max_concurrent_jobs = int(os.getenv("WORKER_MAX_CONCURRENT_JOBS", "3"))
        self.worker_max_retry_attempts = int(os.getenv("WORKER_MAX_RETRY_ATTEMPTS", "5"))
        self.worker_base_retry_delay = int(os.getenv("WORKER_BASE_RETRY_DELAY", "60"))
        self.worker_stats_log_interval = int(os.getenv("WORKER_STATS_LOG_INTERVAL", "300"))
        
        # Pulse API configuration
        self.pulse_api_base_url = os.getenv("PULSE_API_BASE_URL", "https://dev.pulse-core.getpulseinsights.ai")
        
        self.secrets: Dict[str, Any] = {}
        self.tenant_id: Optional[str] = None
        
    def _get_supabase_client(self) -> Client:
        """Get or create Supabase client."""
        return create_client(self.supabase_url, self.supabase_key)
    
    def _resolve_tenant_from_org(self, org_name: str) -> str:
        """
        Resolve tenant_id from org_id using org_directory table.
        
        Args:
            org_id: Organization ID from header
            
        Returns:
            tenant_id for the organization
        """
        try:
            client = self._get_supabase_client()

            resp = (
                client.table("orgs")
                .select("id, status")
                .eq("org_name", org_name)
                .single()  
                .execute()
            )
            
            print(resp)
            
            row = resp.data
            if not row or row.get("status") != "active":
                raise ValueError(f"Org {org_name} not found or inactive")

            return row["id"]
            
        except Exception as e:
            logger.error(f"Failed to resolve tenant for org {org_name}: {e}")
            raise ValueError(f"Tenant resolution failed: {e}")
    
    def load_tenant_secrets(self, org_name: str) -> bool:
        """
        Load tenant-specific secrets for the given org_id.
        
        Args:
            org_id: Organization ID from request header
            
        Returns:
            True if secrets loaded successfully
        """
        try:
            # Resolve tenant_id from org_id
            id = self._resolve_tenant_from_org(org_name)
            self.org_id = id
            print(id)
            
            # Check cache first
            cached = _secrets_cache.get(id)
            if cached and cached[1] > time.time():
                self.secrets = cached[0]
                logger.info(f"✅ Loaded {len(self.secrets)} secrets from cache for tenant {id}")
                return True
            
            # Load from database
            client = self._get_supabase_client()
            result = client.table("tenant_secrets").select("*").eq("org_id", id).single().execute()
            
            if result.data:
                self.secrets = result.data
                # Cache the result
                _secrets_cache[id] = (self.secrets, time.time() + SECRETS_CACHE_TTL)
                logger.info(f"✅ Loaded {len(self.secrets)} secrets from database for tenant {id}")
                return True
            else:
                logger.error(f"No secrets found for tenant {id}")
                return False
                
        except Exception as e:
            logger.error(f"Error loading tenant secrets for org {org_name}: {e}")
            return False
    
    def get_secret(self, key: str, default: Any = None) -> Any:
        """Get a secret value by key."""
        return self.secrets.get(key, default)
    
    def get_pulse_api_config(self) -> Dict[str, str]:
        """Get Pulse API configuration."""
        return {
            "base_url": self.pulse_api_base_url
        }
    
config = Config()
