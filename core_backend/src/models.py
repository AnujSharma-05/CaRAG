from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", back_populates="created_groups")
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="group", cascade="all, delete-orphan")

class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="memberships")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    created_groups = relationship("Group", back_populates="creator")
    memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", secondary="document_categories", back_populates="categories")
    group = relationship("Group")

class DocumentCategory(Base):
    __tablename__ = "document_categories"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_size = Column(Integer, nullable=True)
    file_path = Column(String)
    status = Column(String, default="uploaded")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # NEW: Documents now belong to Groups, not individual Users! (nullable=True to preserve Core Backend compatibility)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True)
    
    group = relationship("Group", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    categories = relationship("Category", secondary="document_categories", back_populates="documents")

class DocumentChunk(Base): 
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    milvus_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")
