from typing import List, Optional

from pydantic import BaseModel, Field


class ChatAttachment(BaseModel):
    name: str = Field(default="image")
    mime_type: str = Field(min_length=1)
    data_url: str = Field(min_length=1)
    size: int = Field(default=0, ge=0)


class ChatPayload(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    attachments: List[ChatAttachment] = Field(default_factory=list)
    hidden_user: bool = False
    cached_opening: bool = False
    web_search: bool = False
    analysis_mode: bool = False
    web_search_proxy: str = Field(default="")
    max_tokens: int = Field(default=8192, ge=1, le=65536)
    temperature: float = Field(default=1.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.75, ge=0.0, le=1.0)


class MemoryAdminPayload(BaseModel):
    content: str = Field(min_length=1)
    importance_label: str = Field(default="other", min_length=1)
    visitor_ip: Optional[str] = None


class AdminLoginPayload(BaseModel):
    password: str = Field(min_length=1)


class AuthPasswordPayload(BaseModel):
    old_password: str = Field(default="")
    new_password: str = Field(min_length=6)


class IdlePromptPayload(BaseModel):
    prompt: str = Field(default="")
