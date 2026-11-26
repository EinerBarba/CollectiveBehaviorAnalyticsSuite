import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas._enums import RoleScope


class LaboratoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None


class LaboratoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None


class LaboratoryOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleOut(BaseModel):
    id: uuid.UUID
    key: str
    display_name: str
    applicable_scope: RoleScope
    description: str | None

    class Config:
        from_attributes = True


class RoleAssignmentCreate(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID
    scope_type: RoleScope
    scope_id: uuid.UUID | None = None


class RoleAssignmentOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    scope_type: RoleScope
    scope_id: uuid.UUID | None
    granted_by: uuid.UUID
    granted_at: datetime
    revoked_at: datetime | None

    class Config:
        from_attributes = True
