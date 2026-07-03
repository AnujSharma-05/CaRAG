# This file contains everything for the group management and their concerned endpoints.
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from . import models, schemas
from .database import get_db
from .auth import get_current_user
from src.services import milvus_store
from src import services
import asyncio

router = APIRouter()

@router.post("/", response_model=schemas.GroupResponse) # This endpoint is for creating a new group. We create a group and add the creator as the first member of the group.
async def create_group(
    group: schemas.GroupCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
     # 0. Check for duplicate group name globally
    existing_group = db.query(models.Group).filter(models.Group.name == group.name).first()
    if existing_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A group with the name '{group.name}' already exists."
        )
    # 1. Create the Group
    new_group = models.Group(name=group.name, created_by=current_user.id)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    # 2. Add the creator as the first GroupMember
    member = models.GroupMember(group_id=new_group.id, user_id=current_user.id)
    db.add(member)
    db.commit()

    return new_group


@router.get("/", response_model=List[schemas.GroupResponse]) # This endpoint is for listing all groups the user is a member of.
async def list_groups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Retrieve all groups where the current user is a member
    groups = db.query(models.Group).join(models.GroupMember).filter(
        models.GroupMember.user_id == current_user.id
    ).all()
    
    # Calculate counts dynamically
    for group in groups:
        group.member_count = len(group.members)
        group.doc_count = len(group.documents)
        
    return groups


@router.get("/{group_id}", response_model=schemas.GroupDetailResponse) # This endpoint is for getting the details of a specific group. It returns the group information along with the list of members in the group.
async def get_group_detail(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Check if group exists
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
        
    # 2. Validate membership
    member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == current_user.id
    ).first()
    
    if not member:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")
    group.member_count = len(group.members)
    group.doc_count = len(group.documents)
    
    # We map the user's email into the members list for the frontend
    for m in group.members:
        m.email = m.user.email

    return group


@router.post("/{group_id}/invite", response_model=schemas.GroupMemberResponse)
async def invite_member(
    group_id: int,
    invite: schemas.InviteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Check if group exists
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    # 2. Check if current user is a member (only members can invite)
    is_member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == current_user.id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="You are not a member of this group.")

    # 3. Prevent inviting yourself
    if invite.email.lower() == current_user.email.lower():
        raise HTTPException(status_code=400, detail="You are already in this group.")

    # 4. Check if invitee exists
    invitee = db.query(models.User).filter(models.User.email == invite.email.lower()).first()
    if not invitee:
        raise HTTPException(status_code=404, detail="That email isn't registered on CaRAG Live yet.")

    # 5. Check if invitee is already in the group
    existing_member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == invitee.id
    ).first()
    if existing_member:
        raise HTTPException(status_code=409, detail="They're already in this group.")

    # 6. Add them!
    new_member = models.GroupMember(group_id=group_id, user_id=invitee.id)
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    
    new_member.email = invitee.email
    return new_member


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
        
    # Only the creator can delete the group
    if group.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the group creator can delete it.")

    # IMPORTANT: We must clean up Milvus and disk files BEFORE deleting the database row, because once 
    # the row is deleted, we lose the file_path reference needed for deletion.
    for doc in group.documents:
        await services.delete_document_assets(document_id=doc.id, file_path=doc.file_path)

    db.delete(group)
    db.commit()

    return {"message": "Group deleted successfully"}
