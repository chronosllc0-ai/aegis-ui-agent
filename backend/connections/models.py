"""Persistence models and payload schemas for admin/user connection management."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, String, Text, func

from backend.database import Base


class ConnectionTemplate(Base):
    """Admin-authored connection templates (drafts + published)."""

    __tablename__ = "connection_templates"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    connection_type = Column(String(20), nullable=False)  # oauth|bot|mcp
    config_json = Column(Text, nullable=False, default="{}")
    status = Column(String(20), nullable=False, default="draft")
    published = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MCPServerConfig(Base):
    """User-instantiated MCP server records from custom config or global presets."""

    __tablename__ = "mcp_server_configs"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    source_type = Column(String(30), nullable=False, default="user_custom")
    owner_scope = Column(String(20), nullable=False, default="user")
    preset_id = Column(String(255), nullable=True)
    transport = Column(String(20), nullable=False, default="http")
    endpoint = Column(Text, nullable=True)
    command = Column(Text, nullable=True)
    args_json = Column(Text, nullable=False, default="[]")
    auth_type = Column(String(20), nullable=False, default="none")
    secret_ref = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="added")
    last_error = Column(Text, nullable=True)
    tools_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AdminConnectionDraftPayload(BaseModel):
    """Wizard payload for creating/updating admin connection templates."""

    id: str | None = None
    name: str = Field(min_length=1)
    subtitle: str | None = None
    description: str | None = None
    logo_url: str | None = None
    connection_type: Literal["oauth", "bot", "mcp"]
    config: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published"] = "draft"


class ConnectionTestPayload(BaseModel):
    """Payload used to run per-type connection validation tests."""

    connection_type: Literal["oauth", "bot", "mcp"]
    config: dict[str, Any] = Field(default_factory=dict)


class MCPPresetApplyPayload(BaseModel):
    """Request payload for creating a user MCP instance from preset template."""

    preset_id: str


class MCPCustomCreatePayload(BaseModel):
    """Request payload for user-scoped custom MCP creation."""

    name: str = Field(min_length=1)
    server_url: str = Field(min_length=1)
    auth_type: Literal["none", "api_key", "oauth"] = "none"
    api_key: str | None = None


class MCPScanResponse(BaseModel):
    """Response payload for MCP tool discovery."""

    ok: bool
    tools: list[dict[str, Any]]
    message: str
    error: str | None = None
    tested_at: datetime
