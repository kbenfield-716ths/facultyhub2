# """
# Draft system routes for rolling availability selection
# """

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from ..models import SessionLocal, Faculty, DraftRound, DraftSlot
from ..auth import get_current_user
from ..email_service import send_draft_notification

router = APIRouter(prefix="/api/draft", tags=["draft"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== Schemas =====

class DraftRoundOut(BaseModel):
    id: str
    year: int
    round_number: int
    status: str
    window_size: int
    hours_per_slot: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class DraftSlotOut(BaseModel):
    id: str
    round_id: str
    faculty_id: str
    faculty_name: str
    priority_order: int
    status: str
    notified_at: Optional[datetime]
    deadline: Optional[datetime]
    submitted_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class CreateDraftRequest(BaseModel):
    year: int
    faculty_priority: List[str]  # List of faculty IDs in priority order
    window_size: int = 5
    hours_per_slot: int = 72


class UpdatePriorityRequest(BaseModel):
    faculty_priority: List[str]  # List of faculty IDs in new order


# ===== Helper Functions =====

def activate_next_slots(db: Session, round_id: str, window_size: int, hours_per_slot: int):
    """Activate next faculty members in the draft"""
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    # Count currently active slots
    active_count = db.query(DraftSlot).filter(
        DraftSlot.round_id == round_id,
        DraftSlot.status == 'active'
    ).count()
    
    # How many more can we activate?
    slots_to_activate = window_size - active_count
    
    if slots_to_activate <= 0:
        return []
    
    # Get next waiting slots
    waiting_slots = db.query(DraftSlot).filter(
        DraftSlot.round_id == round_id,
        DraftSlot.status == 'waiting'
    ).order_by(DraftSlot.priority_order).limit(slots_to_activate).all()
    
    activated = []
    now = datetime.utcnow()
    
    for slot in waiting_slots:
        slot.status = 'active'
        slot.notified_at = now
        slot.deadline = now + timedelta(hours=hours_per_slot)
        activated.append(slot)
        
        # Send email notification
        try:
            send_draft_notification(
                faculty_id=slot.faculty_id,
                priority=slot.priority_order,
                deadline=slot.deadline,
                round_year=draft_round.year
            )
        except Exception as e:
            print(f"Failed to send notification to {slot.faculty_id}: {e}")
    
    db.commit()
    return activated


def check_expired_slots(db: Session, round_id: str):
    """Check for expired slots and mark them"""
    now = datetime.utcnow()
    
    expired_slots = db.query(DraftSlot).filter(
        DraftSlot.round_id == round_id,
        DraftSlot.status == 'active',
        DraftSlot.deadline < now
    ).all()
    
    for slot in expired_slots:
        slot.status = 'expired'
    
    if expired_slots:
        db.commit()
    
    return expired_slots


# ===== Admin Routes =====

@router.post("/admin/rounds", response_model=DraftRoundOut)
def create_draft_round(
    request: CreateDraftRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new draft round (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    # Check if active round exists for this year
    existing = db.query(DraftRound).filter(
        DraftRound.year == request.year,
        DraftRound.status.in_(['pending', 'active', 'paused'])
    ).first()
    
    if existing:
        raise HTTPException(400, f"Draft round already exists for {request.year}")
    
    # Validate faculty IDs and exclude draft_exempt faculty
    faculty_ids = set(request.faculty_priority)

    # Check for draft_exempt faculty in the list
    draft_exempt_faculty = db.query(Faculty.id, Faculty.name).filter(
        Faculty.id.in_(faculty_ids),
        Faculty.draft_exempt == True
    ).all()

    if draft_exempt_faculty:
        exempt_names = ", ".join([f"{name} ({id})" for id, name in draft_exempt_faculty])
        raise HTTPException(
            400,
            f"The following faculty are draft exempt and should not be included: {exempt_names}"
        )

    # Validate that all faculty are active and exist
    existing_faculty = db.query(Faculty.id).filter(
        Faculty.id.in_(faculty_ids),
        Faculty.active == True,
        Faculty.draft_exempt == False
    ).all()

    if len(existing_faculty) != len(faculty_ids):
        raise HTTPException(400, "Some faculty IDs are invalid, inactive, or draft exempt")
    
    # Create draft round
    draft_round = DraftRound(
        id=str(uuid.uuid4()),
        year=request.year,
        round_number=1,
        status='pending',
        window_size=request.window_size,
        hours_per_slot=request.hours_per_slot
    )
    
    db.add(draft_round)
    db.flush()
    
    # Create slots for each faculty
    for idx, faculty_id in enumerate(request.faculty_priority, start=1):
        slot = DraftSlot(
            id=str(uuid.uuid4()),
            round_id=draft_round.id,
            faculty_id=faculty_id,
            priority_order=idx,
            status='waiting'
        )
        db.add(slot)
    
    db.commit()
    db.refresh(draft_round)
    
    return draft_round


@router.get("/admin/rounds", response_model=List[DraftRoundOut])
def get_draft_rounds(
    year: Optional[int] = None,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all draft rounds (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    query = db.query(DraftRound)
    
    if year:
        query = query.filter(DraftRound.year == year)
    
    rounds = query.order_by(DraftRound.year.desc(), DraftRound.round_number.desc()).all()
    
    return rounds


@router.get("/admin/rounds/{round_id}", response_model=DraftRoundOut)
def get_draft_round(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific draft round details (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    return draft_round


@router.get("/admin/rounds/{round_id}/slots", response_model=List[DraftSlotOut])
def get_draft_slots(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all slots for a draft round (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    slots = db.query(DraftSlot).filter(
        DraftSlot.round_id == round_id
    ).order_by(DraftSlot.priority_order).all()
    
    result = []
    for slot in slots:
        faculty = db.query(Faculty).filter(Faculty.id == slot.faculty_id).first()
        result.append(DraftSlotOut(
            id=slot.id,
            round_id=slot.round_id,
            faculty_id=slot.faculty_id,
            faculty_name=faculty.name if faculty else "Unknown",
            priority_order=slot.priority_order,
            status=slot.status,
            notified_at=slot.notified_at,
            deadline=slot.deadline,
            submitted_at=slot.submitted_at
        ))
    
    return result


@router.post("/admin/rounds/{round_id}/start")
def start_draft_round(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a draft round (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    if draft_round.status != 'pending':
        raise HTTPException(400, f"Cannot start draft in status: {draft_round.status}")
    
    # Start the draft
    draft_round.status = 'active'
    draft_round.started_at = datetime.utcnow()
    
    db.commit()
    
    # Activate first batch of slots
    activated = activate_next_slots(
        db, 
        round_id, 
        draft_round.window_size, 
        draft_round.hours_per_slot
    )
    
    return {
        "status": "started",
        "activated_count": len(activated),
        "started_at": draft_round.started_at
    }


@router.post("/admin/rounds/{round_id}/pause")
def pause_draft_round(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pause a draft round (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    if draft_round.status != 'active':
        raise HTTPException(400, "Can only pause active drafts")
    
    draft_round.status = 'paused'
    db.commit()
    
    return {"status": "paused"}


@router.post("/admin/rounds/{round_id}/resume")
def resume_draft_round(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resume a paused draft round (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    if draft_round.status != 'paused':
        raise HTTPException(400, "Can only resume paused drafts")
    
    draft_round.status = 'active'
    db.commit()
    
    return {"status": "resumed"}


@router.post("/admin/rounds/{round_id}/complete")
def complete_draft_round(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark draft round as completed (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    draft_round.status = 'completed'
    draft_round.completed_at = datetime.utcnow()
    
    db.commit()
    
    return {"status": "completed", "completed_at": draft_round.completed_at}


@router.patch("/admin/rounds/{round_id}/priority")
def update_draft_priority(
    round_id: str,
    request: UpdatePriorityRequest,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update faculty priority order (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    if draft_round.status not in ['pending', 'paused']:
        raise HTTPException(400, "Cannot update priority for active or completed drafts")
    
    # Get all slots for this round
    slots = db.query(DraftSlot).filter(DraftSlot.round_id == round_id).all()
    slot_map = {slot.faculty_id: slot for slot in slots}
    
    # Validate all faculty IDs are present
    if set(request.faculty_priority) != set(slot_map.keys()):
        raise HTTPException(400, "Faculty list doesn't match existing slots")
    
    # Update priority order
    for idx, faculty_id in enumerate(request.faculty_priority, start=1):
        slot_map[faculty_id].priority_order = idx
    
    db.commit()
    
    return {"status": "updated"}


@router.delete("/admin/rounds/{round_id}")
def delete_draft_round(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a draft round (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    if draft_round.status == 'active':
        raise HTTPException(400, "Cannot delete active draft round. Pause it first.")
    
    db.delete(draft_round)
    db.commit()
    
    return {"status": "deleted"}


@router.post("/admin/rounds/{round_id}/check-expired")
def check_expired_slots_endpoint(
    round_id: str,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually check for expired slots and activate next (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")
    
    draft_round = db.query(DraftRound).filter(DraftRound.id == round_id).first()
    
    if not draft_round:
        raise HTTPException(404, "Draft round not found")
    
    # Check for expired slots
    expired = check_expired_slots(db, round_id)
    
    # Activate next slots
    activated = activate_next_slots(
        db,
        round_id,
        draft_round.window_size,
        draft_round.hours_per_slot
    )
    
    return {
        "expired_count": len(expired),
        "activated_count": len(activated)
    }


# ===== Faculty Routes =====

@router.get("/my-status")
def get_my_draft_status(
    year: Optional[int] = None,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's draft status"""
    
    # Get current or specified year's active draft
    query = db.query(DraftRound).filter(
        DraftRound.status.in_(['active', 'paused'])
    )
    
    if year:
        query = query.filter(DraftRound.year == year)
    
    draft_round = query.order_by(DraftRound.created_at.desc()).first()
    
    if not draft_round:
        return {
            "has_active_draft": False,
            "message": "No active draft round"
        }
    
    # Get user's slot
    my_slot = db.query(DraftSlot).filter(
        DraftSlot.round_id == draft_round.id,
        DraftSlot.faculty_id == current_user.id
    ).first()
    
    if not my_slot:
        return {
            "has_active_draft": True,
            "in_draft": False,
            "message": "You are not in this draft round"
        }
    
    # Get other active slots
    active_slots = db.query(DraftSlot).join(Faculty).filter(
        DraftSlot.round_id == draft_round.id,
        DraftSlot.status == 'active'
    ).order_by(DraftSlot.priority_order).all()
    
    other_active = []
    for slot in active_slots:
        if slot.faculty_id != current_user.id:
            faculty = db.query(Faculty).filter(Faculty.id == slot.faculty_id).first()
            other_active.append({
                "name": faculty.name if faculty else "Unknown",
                "priority": slot.priority_order,
                "deadline": slot.deadline,
                "submitted": slot.status == 'submitted'
            })
    
    # Calculate time remaining if active
    time_remaining = None
    if my_slot.status == 'active' and my_slot.deadline:
        remaining = my_slot.deadline - datetime.utcnow()
        time_remaining = {
            "total_seconds": remaining.total_seconds(),
            "hours": int(remaining.total_seconds() // 3600),
            "minutes": int((remaining.total_seconds() % 3600) // 60)
        }
    
    return {
        "has_active_draft": True,
        "in_draft": True,
        "round_id": draft_round.id,
        "year": draft_round.year,
        "draft_status": draft_round.status,
        "my_priority": my_slot.priority_order,
        "my_status": my_slot.status,
        "notified_at": my_slot.notified_at,
        "deadline": my_slot.deadline,
        "submitted_at": my_slot.submitted_at,
        "time_remaining": time_remaining,
        "other_active": other_active,
        "window_size": draft_round.window_size
    }


@router.post("/submit")
def submit_draft_selections(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark that faculty member has submitted their selections"""
    
    # Find active draft slot for this user
    my_slot = db.query(DraftSlot).join(DraftRound).filter(
        DraftSlot.faculty_id == current_user.id,
        DraftSlot.status == 'active',
        DraftRound.status == 'active'
    ).first()
    
    if not my_slot:
        raise HTTPException(400, "No active draft slot found for you")
    
    # Mark as submitted
    my_slot.status = 'submitted'
    my_slot.submitted_at = datetime.utcnow()
    
    db.commit()
    
    # Get the draft round
    draft_round = db.query(DraftRound).filter(DraftRound.id == my_slot.round_id).first()
    
    # Activate next person
    activated = activate_next_slots(
        db,
        my_slot.round_id,
        draft_round.window_size,
        draft_round.hours_per_slot
    )
    
    # Check if draft is complete
    remaining = db.query(DraftSlot).filter(
        DraftSlot.round_id == my_slot.round_id,
        DraftSlot.status.in_(['waiting', 'active'])
    ).count()
    
    if remaining == 0:
        draft_round.status = 'completed'
        draft_round.completed_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "submitted",
            "draft_completed": True,
            "activated_count": len(activated)
        }
    
    return {
        "status": "submitted",
        "draft_completed": False,
        "activated_count": len(activated)
    }
