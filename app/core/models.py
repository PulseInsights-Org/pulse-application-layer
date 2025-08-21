"""
Database models for the ingestion pipeline.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class Intake(BaseModel):
    """Intake model representing the intakes table."""
    id: UUID
    org_id: str
    status: str
    storage_path: str
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    idempotency_key: UUID
    attempts: int = 0
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class Memory(BaseModel):
    """Memory model representing the memories table."""
    id: UUID
    intake_id: UUID
    org_id: str
    title: str
    summary: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

class IntakeCreate(BaseModel):
    """Model for creating a new intake."""
    org_id: str
    storage_path: str
    idempotency_key: UUID

class IntakeUpdate(BaseModel):
    """Model for updating an intake."""
    status: Optional[str] = None
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    attempts: Optional[int] = None
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None

class MemoryCreate(BaseModel):
    """Model for creating a new memory."""
    intake_id: UUID
    org_id: str
    title: str
    summary: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
