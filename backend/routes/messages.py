# backend/routes/messages.py
"""
Message board routes for faculty communication.
Supports threaded discussions with reactions and read tracking.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid

from ..models import (
    SessionLocal, Faculty, MessageBoard, Message, 
    MessageReaction, MessageReadStatus
)
from ..auth import get_current_user

router = APIRouter(prefix="/api/messages", tags=["messages"])

# ===== Database dependency =====

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== Pydantic schemas =====

class BoardOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    requires_moonlighting: bool
    unread_count: int = 0
    
    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: str
    board_id: str
    author_id: str
    author_name: str
    parent_id: Optional[str]
    subject: Optional[str]
    content: str
    is_pinned: bool
    is_edited: bool
    edited_at: Optional[datetime]
    created_at: datetime
    
    # Computed fields
    reply_count: int = 0
    reaction_counts: dict = {}
    has_read: bool = False
    
    class Config:
        from_attributes = True


class ThreadOut(BaseModel):
    """Thread with summary info"""
    id: str
    board_id: str
    author_id: str
    author_name: str
    subject: str
    content: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    
    # Counts
    reply_count: int = 0
    reaction_count: int = 0
    
    # Last reply info
    last_reply_at: Optional[datetime] = None
    last_reply_by: Optional[str] = None
    
    class Config:
        from_attributes = True


class CreateThreadRequest(BaseModel):
    board_id: str
    subject: str
    content: str


class CreateReplyRequest(BaseModel):
    parent_id: str
    content: str


class ReactRequest(BaseModel):
    message_id: str
    reaction: str  # Emoji like '👍', '❤️', '🎉'


# ===== Helper functions =====

def can_access_board(faculty: Faculty, board: MessageBoard) -> bool:
    """Check if faculty can access a board"""
    if not board.requires_moonlighting:
        return True
    return faculty.does_moonlighting


def get_message_with_counts(db: Session, message: Message, current_user_id: str) -> MessageOut:
    """Get message with computed fields"""
    # Count replies
    reply_count = db.query(Message).filter(Message.parent_id == message.id).count()
    
    # Get reaction counts
    reaction_counts = {}
    reactions = db.query(
        MessageReaction.reaction,
        func.count(MessageReaction.id).label('count')
    ).filter(
        MessageReaction.message_id == message.id
    ).group_by(MessageReaction.reaction).all()
    
    for reaction, count in reactions:
        reaction_counts[reaction] = count
    
    # Check if current user has read
    has_read = db.query(MessageReadStatus).filter(
        MessageReadStatus.message_id == message.id,
        MessageReadStatus.faculty_id == current_user_id
    ).first() is not None
    
    return MessageOut(
        id=message.id,
        board_id=message.board_id,
        author_id=message.author_id,
        author_name=message.author.name,
        parent_id=message.parent_id,
        subject=message.subject,
        content=message.content,
        is_pinned=message.is_pinned,
        is_edited=message.is_edited,
        edited_at=message.edited_at,
        created_at=message.created_at,
        reply_count=reply_count,
        reaction_counts=reaction_counts,
        has_read=has_read
    )


# ===== Routes =====

@router.get("/boards", response_model=List[BoardOut])
def get_accessible_boards(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all boards the current user can access"""
    boards = db.query(MessageBoard).filter(
        MessageBoard.is_active == True
    ).order_by(MessageBoard.display_order).all()
    
    result = []
    for board in boards:
        # Check access
        if not can_access_board(current_user, board):
            continue
        
        # Count unread messages
        unread_count = db.query(Message).filter(
            Message.board_id == board.id,
            ~Message.id.in_(
                db.query(MessageReadStatus.message_id).filter(
                    MessageReadStatus.faculty_id == current_user.id
                )
            )
        ).count()
        
        result.append(BoardOut(
            id=board.id,
            name=board.name,
            description=board.description,
            icon=board.icon,
            requires_moonlighting=board.requires_moonlighting,
            unread_count=unread_count
        ))
    
    return result


@router.get("/boards/{board_id}/threads", response_model=List[ThreadOut])
def get_threads(
    board_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all threads (top-level messages) for a board"""
    # Get board and check access
    board = db.query(MessageBoard).filter(MessageBoard.id == board_id).first()
    if not board:
        raise HTTPException(404, "Board not found")
    
    if not can_access_board(current_user, board):
        raise HTTPException(403, "Access denied to this board")
    
    # Get threads (messages with no parent)
    threads = db.query(Message).filter(
        Message.board_id == board_id,
        Message.parent_id == None
    ).order_by(
        Message.is_pinned.desc(),
        Message.updated_at.desc()
    ).all()
    
    result = []
    for thread in threads:
        # Count replies
        reply_count = db.query(Message).filter(Message.parent_id == thread.id).count()
        
        # Count total reactions
        reaction_count = db.query(MessageReaction).filter(
            MessageReaction.message_id == thread.id
        ).count()
        
        # Get last reply info
        last_reply = db.query(Message).filter(
            Message.parent_id == thread.id
        ).order_by(Message.created_at.desc()).first()
        
        last_reply_at = last_reply.created_at if last_reply else None
        last_reply_by = last_reply.author.name if last_reply else None
        
        result.append(ThreadOut(
            id=thread.id,
            board_id=thread.board_id,
            author_id=thread.author_id,
            author_name=thread.author.name,
            subject=thread.subject,
            content=thread.content,
            is_pinned=thread.is_pinned,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            reply_count=reply_count,
            reaction_count=reaction_count,
            last_reply_at=last_reply_at,
            last_reply_by=last_reply_by
        ))
    
    return result


@router.get("/threads/{thread_id}", response_model=MessageOut)
def get_thread(
    thread_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific thread with details"""
    message = db.query(Message).filter(Message.id == thread_id).first()
    if not message:
        raise HTTPException(404, "Thread not found")
    
    # Check board access
    board = db.query(MessageBoard).filter(MessageBoard.id == message.board_id).first()
    if not can_access_board(current_user, board):
        raise HTTPException(403, "Access denied")
    
    return get_message_with_counts(db, message, current_user.id)


@router.get("/threads/{thread_id}/replies", response_model=List[MessageOut])
def get_replies(
    thread_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all replies to a thread"""
    # Check thread exists and user has access
    thread = db.query(Message).filter(Message.id == thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")
    
    board = db.query(MessageBoard).filter(MessageBoard.id == thread.board_id).first()
    if not can_access_board(current_user, board):
        raise HTTPException(403, "Access denied")
    
    # Get replies
    replies = db.query(Message).filter(
        Message.parent_id == thread_id
    ).order_by(Message.created_at.asc()).all()
    
    return [get_message_with_counts(db, reply, current_user.id) for reply in replies]


@router.post("/threads")
def create_thread(
    request: CreateThreadRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new thread"""
    # Check board exists and user has access
    board = db.query(MessageBoard).filter(MessageBoard.id == request.board_id).first()
    if not board:
        raise HTTPException(404, "Board not found")
    
    if not can_access_board(current_user, board):
        raise HTTPException(403, "Access denied to this board")
    
    # Validate input
    if not request.subject or not request.subject.strip():
        raise HTTPException(400, "Subject is required")
    if not request.content or not request.content.strip():
        raise HTTPException(400, "Content is required")
    
    # Create message
    message = Message(
        id=str(uuid.uuid4()),
        board_id=request.board_id,
        author_id=current_user.id,
        parent_id=None,
        subject=request.subject.strip(),
        content=request.content.strip()
    )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    return {"status": "ok", "thread_id": message.id}


@router.post("/replies")
def create_reply(
    request: CreateReplyRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reply to a thread"""
    # Check parent exists and user has access
    parent = db.query(Message).filter(Message.id == request.parent_id).first()
    if not parent:
        raise HTTPException(404, "Parent message not found")
    
    board = db.query(MessageBoard).filter(MessageBoard.id == parent.board_id).first()
    if not can_access_board(current_user, board):
        raise HTTPException(403, "Access denied")
    
    # Validate input
    if not request.content or not request.content.strip():
        raise HTTPException(400, "Content is required")
    
    # Get the root thread (for parent_id - replies go to thread, not to other replies)
    root_thread = parent if parent.parent_id is None else db.query(Message).filter(Message.id == parent.parent_id).first()
    
    # Create reply
    message = Message(
        id=str(uuid.uuid4()),
        board_id=parent.board_id,
        author_id=current_user.id,
        parent_id=root_thread.id,  # Always reply to the root thread
        subject=None,  # Replies don't have subjects
        content=request.content.strip()
    )
    
    db.add(message)
    
    # Update thread's updated_at
    root_thread.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(message)
    
    return {"status": "ok", "message_id": message.id}


@router.post("/react")
def toggle_reaction(
    request: ReactRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add or remove a reaction to a message"""
    # Check message exists and user has access
    message = db.query(Message).filter(Message.id == request.message_id).first()
    if not message:
        raise HTTPException(404, "Message not found")
    
    board = db.query(MessageBoard).filter(MessageBoard.id == message.board_id).first()
    if not can_access_board(current_user, board):
        raise HTTPException(403, "Access denied")
    
    # Check if reaction already exists
    existing = db.query(MessageReaction).filter(
        MessageReaction.message_id == request.message_id,
        MessageReaction.faculty_id == current_user.id,
        MessageReaction.reaction == request.reaction
    ).first()
    
    if existing:
        # Remove reaction (toggle off)
        db.delete(existing)
        db.commit()
        return {"status": "removed"}
    else:
        # Add reaction
        reaction = MessageReaction(
            id=str(uuid.uuid4()),
            message_id=request.message_id,
            faculty_id=current_user.id,
            reaction=request.reaction
        )
        db.add(reaction)
        db.commit()
        return {"status": "added"}


@router.post("/mark-read/{message_id}")
def mark_message_read(
    message_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a message as read"""
    # Check message exists
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(404, "Message not found")
    
    # Check if already marked
    existing = db.query(MessageReadStatus).filter(
        MessageReadStatus.message_id == message_id,
        MessageReadStatus.faculty_id == current_user.id
    ).first()
    
    if not existing:
        read_status = MessageReadStatus(
            id=str(uuid.uuid4()),
            message_id=message_id,
            faculty_id=current_user.id
        )
        db.add(read_status)
        db.commit()
    
    return {"status": "ok"}


@router.post("/mark-thread-read/{thread_id}")
def mark_thread_read(
    thread_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark entire thread and all replies as read"""
    # Check thread exists
    thread = db.query(Message).filter(Message.id == thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")
    
    # Get all message IDs (thread + replies)
    message_ids = [thread.id]
    replies = db.query(Message.id).filter(Message.parent_id == thread_id).all()
    message_ids.extend([r[0] for r in replies])
    
    # Mark all as read
    for msg_id in message_ids:
        existing = db.query(MessageReadStatus).filter(
            MessageReadStatus.message_id == msg_id,
            MessageReadStatus.faculty_id == current_user.id
        ).first()
        
        if not existing:
            read_status = MessageReadStatus(
                id=str(uuid.uuid4()),
                message_id=msg_id,
                faculty_id=current_user.id
            )
            db.add(read_status)
    
    db.commit()
    return {"status": "ok"}


# ===== Admin endpoints =====

@router.post("/admin/pin/{message_id}")
def toggle_pin(
    message_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pin or unpin a message (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(404, "Message not found")
    
    message.is_pinned = not message.is_pinned
    db.commit()
    
    return {"status": "ok", "is_pinned": message.is_pinned}


@router.get("/admin/stats")
def get_message_stats(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get message board statistics (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    total_threads = db.query(Message).filter(Message.parent_id == None).count()
    total_messages = db.query(Message).count()
    
    # Active users (those who have posted)
    active_users = db.query(Message.author_id).distinct().count()
    
    # Moonlighting faculty count
    moonlighting_count = db.query(Faculty).filter(
        Faculty.does_moonlighting == True,
        Faculty.active == True
    ).count()
    
    return {
        "total_threads": total_threads,
        "total_messages": total_messages,
        "active_users": active_users,
        "moonlighting_faculty": moonlighting_count
    }
