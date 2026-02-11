"""
Service Week Overrides API
Handles faculty blocks and manual assignments for service week scheduling
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List
from pydantic import BaseModel
from datetime import datetime
import uuid

from backend.models import get_db, Faculty, ServiceWeek, FacultyBlock, ServiceWeekAssignment
from backend.auth import require_admin, get_current_user

router = APIRouter(prefix="/api/admin/service-weeks", tags=["service-week-overrides"])


# ==================== REQUEST/RESPONSE MODELS ====================

class CreateBlockRequest(BaseModel):
    faculty_id: str
    week_id: str
    reason: str = ""


class BlockResponse(BaseModel):
    id: str
    faculty_id: str
    faculty_name: str
    week_id: str
    week_label: str
    reason: str
    created_by: str = None
    created_by_name: str = None
    created_at: str


class CreateAssignmentRequest(BaseModel):
    faculty_id: str
    week_id: str
    service_type: str
    reason: str = ""


class AssignmentResponse(BaseModel):
    id: str
    faculty_id: str
    faculty_name: str
    week_id: str
    week_label: str
    service_type: str
    reason: str
    created_by: str = None
    created_by_name: str = None
    created_at: str


# ==================== FACULTY BLOCKS ====================

@router.get("/blocks", response_model=List[BlockResponse])
async def get_faculty_blocks(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Get all faculty blocks for a given year.
    Blocks prevent faculty from being assigned to specific weeks.
    """

    # Query blocks with joins to get faculty and week information
    blocks = db.query(
        FacultyBlock.id,
        FacultyBlock.faculty_id,
        Faculty.name.label('faculty_name'),
        FacultyBlock.week_id,
        ServiceWeek.label.label('week_label'),
        FacultyBlock.reason,
        FacultyBlock.created_by,
        FacultyBlock.created_at
    ).join(
        Faculty, FacultyBlock.faculty_id == Faculty.id
    ).join(
        ServiceWeek, FacultyBlock.week_id == ServiceWeek.id
    ).filter(
        ServiceWeek.year == year
    ).order_by(
        ServiceWeek.week_number
    ).all()

    # Get creator names
    result = []
    for block in blocks:
        created_by_name = None
        if block.created_by:
            creator = db.query(Faculty).filter(Faculty.id == block.created_by).first()
            created_by_name = creator.name if creator else None

        result.append(BlockResponse(
            id=block.id,
            faculty_id=block.faculty_id,
            faculty_name=block.faculty_name,
            week_id=block.week_id,
            week_label=block.week_label,
            reason=block.reason or "",
            created_by=block.created_by,
            created_by_name=created_by_name,
            created_at=block.created_at.isoformat() if block.created_at else datetime.utcnow().isoformat()
        ))

    return result


@router.post("/create-block", response_model=BlockResponse)
async def create_faculty_block(
    request: CreateBlockRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Create a new faculty block to prevent assignment to a specific week.
    """

    # Validate faculty exists
    faculty = db.query(Faculty).filter(Faculty.id == request.faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail=f"Faculty {request.faculty_id} not found")

    # Validate week exists
    week = db.query(ServiceWeek).filter(ServiceWeek.id == request.week_id).first()
    if not week:
        raise HTTPException(status_code=404, detail=f"Week {request.week_id} not found")

    # Check if block already exists
    existing = db.query(FacultyBlock).filter(
        and_(
            FacultyBlock.faculty_id == request.faculty_id,
            FacultyBlock.week_id == request.week_id
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"{faculty.name} is already blocked from {week.label}"
        )

    # Create block
    block = FacultyBlock(
        id=str(uuid.uuid4()),
        faculty_id=request.faculty_id,
        week_id=request.week_id,
        reason=request.reason,
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )

    db.add(block)
    db.commit()
    db.refresh(block)

    return BlockResponse(
        id=block.id,
        faculty_id=block.faculty_id,
        faculty_name=faculty.name,
        week_id=block.week_id,
        week_label=week.label,
        reason=block.reason or "",
        created_by=current_user.id,
        created_by_name=current_user.name,
        created_at=block.created_at.isoformat()
    )


@router.delete("/blocks/{block_id}")
async def delete_faculty_block(
    block_id: str,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Delete a faculty block. Faculty will be eligible for this week again.
    """

    block = db.query(FacultyBlock).filter(FacultyBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    db.delete(block)
    db.commit()

    return {"success": True, "message": "Block deleted successfully"}


# ==================== MANUAL ASSIGNMENTS ====================

@router.get("/manual-assignments", response_model=List[AssignmentResponse])
async def get_manual_assignments(
    year: int = 2026,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Get all manual service week assignments for a given year.
    """

    assignments = db.query(
        ServiceWeekAssignment.id,
        ServiceWeekAssignment.faculty_id,
        Faculty.name.label('faculty_name'),
        ServiceWeekAssignment.week_id,
        ServiceWeek.label.label('week_label'),
        ServiceWeekAssignment.service_type,
        ServiceWeekAssignment.reason,
        ServiceWeekAssignment.created_by,
        ServiceWeekAssignment.created_at
    ).join(
        Faculty, ServiceWeekAssignment.faculty_id == Faculty.id
    ).join(
        ServiceWeek, ServiceWeekAssignment.week_id == ServiceWeek.id
    ).filter(
        and_(
            ServiceWeek.year == year,
            ServiceWeekAssignment.is_manual == True
        )
    ).order_by(
        ServiceWeek.week_number
    ).all()

    # Get creator names
    result = []
    for assignment in assignments:
        created_by_name = None
        if assignment.created_by:
            creator = db.query(Faculty).filter(Faculty.id == assignment.created_by).first()
            created_by_name = creator.name if creator else None

        result.append(AssignmentResponse(
            id=assignment.id,
            faculty_id=assignment.faculty_id,
            faculty_name=assignment.faculty_name,
            week_id=assignment.week_id,
            week_label=assignment.week_label,
            service_type=assignment.service_type,
            reason=assignment.reason or "",
            created_by=assignment.created_by,
            created_by_name=created_by_name,
            created_at=assignment.created_at.isoformat() if assignment.created_at else datetime.utcnow().isoformat()
        ))

    return result


@router.post("/create-manual-assignment", response_model=AssignmentResponse)
async def create_manual_assignment(
    request: CreateAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Create a manual service week assignment (overrides automated scheduler).
    """

    # Validate faculty exists
    faculty = db.query(Faculty).filter(Faculty.id == request.faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail=f"Faculty {request.faculty_id} not found")

    # Validate week exists
    week = db.query(ServiceWeek).filter(ServiceWeek.id == request.week_id).first()
    if not week:
        raise HTTPException(status_code=404, detail=f"Week {request.week_id} not found")

    # Validate service type
    valid_services = ['MICU', 'APP-ICU', 'Procedures', 'Consults']
    if request.service_type not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service type. Must be one of: {', '.join(valid_services)}"
        )

    # Check if assignment already exists
    existing = db.query(ServiceWeekAssignment).filter(
        and_(
            ServiceWeekAssignment.faculty_id == request.faculty_id,
            ServiceWeekAssignment.week_id == request.week_id,
            ServiceWeekAssignment.service_type == request.service_type
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"{faculty.name} is already assigned to {request.service_type} for {week.label}"
        )

    # Create manual assignment
    assignment = ServiceWeekAssignment(
        id=str(uuid.uuid4()),
        faculty_id=request.faculty_id,
        week_id=request.week_id,
        service_type=request.service_type,
        is_manual=True,
        reason=request.reason,
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return AssignmentResponse(
        id=assignment.id,
        faculty_id=assignment.faculty_id,
        faculty_name=faculty.name,
        week_id=assignment.week_id,
        week_label=week.label,
        service_type=assignment.service_type,
        reason=assignment.reason or "",
        created_by=current_user.id,
        created_by_name=current_user.name,
        created_at=assignment.created_at.isoformat()
    )


@router.delete("/manual-assignments/{assignment_id}")
async def delete_manual_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Delete a manual assignment.
    """

    assignment = db.query(ServiceWeekAssignment).filter(
        and_(
            ServiceWeekAssignment.id == assignment_id,
            ServiceWeekAssignment.is_manual == True
        )
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Manual assignment not found")

    db.delete(assignment)
    db.commit()

    return {"success": True, "message": "Manual assignment deleted successfully"}
