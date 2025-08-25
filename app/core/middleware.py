"""
Middleware for tenant resolution and secrets loading.
Based on pulse implementation.
"""

from fastapi import Request, HTTPException
from app.core.config import config
import logging

logger = logging.getLogger(__name__)

async def tenant_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    protected_prefixes = ["/api/ingestion", "/api/intakes", "/api/query"]
    is_protected = any(request.url.path.startswith(p) for p in protected_prefixes)

    if is_protected:
        org_name = request.headers.get("x-org-name")
        if not org_name:
            raise HTTPException(status_code=400, detail="Missing x-org-name header")

        try:
            success = config.load_tenant_secrets(org_name)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to load tenant configuration")

            request.state.id = config.org_id
            request.state.secrets = config.secrets
            request.state.org_name = org_name
            logger.info(f"✅ Tenant resolved: org_name={org_name}, tenant_id={config.tenant_id}")
        except Exception as e:
            logger.error(f"Tenant resolution failed for org {org_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Tenant resolution failed: {str(e)}")

    return await call_next(request)