"""
Middleware for tenant resolution and secrets loading.
Based on pulse implementation.
"""

from fastapi import Request, HTTPException
from app.core.config import config
import logging

logger = logging.getLogger(__name__)

async def tenant_middleware(request: Request, call_next):
    """
    Middleware to resolve tenant and load secrets for protected routes.
    
    This middleware:
    1. Checks for x-org-name header on protected routes
    2. Resolves tenant_id from org_id using org_directory table
    3. Loads tenant-specific secrets from tenant_secrets table
    4. Sets request.state with tenant info and secrets
    """
    
    # Define protected routes that need tenant resolution
    protected_prefixes = ["/api/ingestion", "/api/intakes", "/api/query"]
    
    # Check if this is a protected route
    is_protected = any(request.url.path.startswith(prefix) for prefix in protected_prefixes)
    
    if is_protected:
        org_name = request.headers.get("x-org-name")
        if not org_name:
            raise HTTPException(
                status_code=400, 
                detail="Missing x-org-name header"
            )
        
        try:
            # Load tenant secrets for this org
            success = config.load_tenant_secrets(org_name)
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to load tenant configuration"
                )
            
            request.state.id = config.org_id
            request.state.secrets = config.secrets
            request.state.org_name =  org_name
            
            logger.info(f"✅ Tenant resolved: org_id={org_name}, tenant_id={config.tenant_id}")
            
        except Exception as e:
            logger.error(f"Tenant resolution failed for org {org_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Tenant resolution failed: {str(e)}"
            )
    
    response = await call_next(request)
    return response
