from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Optional

# --- Auth Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel): 
    email: str | None = None


# --- Group Schemas ---
class GroupCreate(BaseModel):
    name: str

class GroupMemberResponse(BaseModel):
    user_id: int
    email: str
    joined_at: datetime
    
    class Config:
        from_attributes = True

class GroupResponse(BaseModel):
    id: int
    name: str
    created_by: int
    created_at: datetime
    
    # We will dynamically calculate these in the router
    member_count: Optional[int] = None
    doc_count: Optional[int] = None

    class Config:
        from_attributes = True

class GroupDetailResponse(GroupResponse):
    members: List[GroupMemberResponse] = []


# --- Invite Schema ---
class InviteRequest(BaseModel):
    email: EmailStr


# --- Document Schemas ---
class DocumentBase(BaseModel):
    filename: str
    status: str
    file_size: int | None = None
    categories: List[str] = []

class DocumentResponse(DocumentBase):
    id: int
    group_id: int

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        # Flatten the categories relationship to a list of strings
        validated = super().model_validate(obj, **kwargs)
        if hasattr(obj, 'categories'):
            validated.categories = [c.name for c in obj.categories]
        return validated

class DocumentStatusUpdate(BaseModel):
    status: str


# --- Chat Schemas ---
# These are Group Scoped 
class ChatRequest(BaseModel):
    question: str
    top_k: int = 5
    # Optional manual overrides — if set, bypass automatic 2-stage routing
    category: str | None = None      # Mode B: pin to a specific category
    document_id: int | None = None   # Mode A: pin to a specific document
    bypass_llm: bool = False

class Citation(BaseModel):
    document_id: int
    chunk_index: int
    score: float
    content_preview: str

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
