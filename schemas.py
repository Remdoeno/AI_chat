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
    mode: str = Field(default="chat")
    attachments: List[ChatAttachment] = Field(default_factory=list)
    hidden_user: bool = False
    cached_opening: bool = False
    web_search: bool = False
    analysis_mode: bool = False
    web_search_proxy: str = Field(default="")
    max_tokens: int = Field(default=8192, ge=1, le=65536)
    temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)


class CharacterChatPayload(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    mode: str = Field(default="chat")
    attachments: List[ChatAttachment] = Field(default_factory=list)


class MemoryAdminPayload(BaseModel):
    content: str = Field(min_length=1)
    importance_label: str = Field(default="other", min_length=1)
    visitor_ip: Optional[str] = None
    device_id: Optional[str] = None
    timeline_at: Optional[str] = None
    timeline_start_at: Optional[str] = None
    timeline_end_at: Optional[str] = None
    timeline_kind: Optional[str] = None


class UserMemoryBindingPayload(BaseModel):
    shared_user_id: str = Field(default="", max_length=120)
    share_chat_history: bool = False
    is_host: bool = False
    inherit_assistant_profile: bool = False


class AdminLoginPayload(BaseModel):
    password: str = Field(min_length=1)


class AuthPasswordPayload(BaseModel):
    old_password: str = Field(default="")
    new_password: str = Field(min_length=6)


class IdlePromptPayload(BaseModel):
    prompt: str = Field(default="")


class IdleStatusPayload(BaseModel):
    paused: bool = False


class IdleFrequencyPayload(BaseModel):
    minutes: int = Field(default=5, ge=1, le=10080)


class ArtifactCommentPayload(BaseModel):
    content: str = Field(min_length=1)
    parent_id: Optional[int] = None
    author: str = Field(default="visitor")


class ModelSlotPayload(BaseModel):
    provider: str = Field(default="local")
    display_name: str = Field(default="")
    base_url: str = Field(default="")
    model: str = Field(default="")
    api_key: Optional[str] = None
    use_proxy: bool = False
    proxy_url: str = Field(default="")


class ModelSettingsPayload(BaseModel):
    chat: ModelSlotPayload
    background: ModelSlotPayload
    image: ModelSlotPayload = Field(default_factory=lambda: ModelSlotPayload(provider="none"))
    web_search_proxy: str = Field(default="")
