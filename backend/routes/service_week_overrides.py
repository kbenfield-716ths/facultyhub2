"""
Service Week Overrides API
Handles faculty blocks and manual assignments for service week scheduling
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy import and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid
import csv
import io

from backend.models import get_db, Faculty, ServiceWeek, FacultyBlock, ServiceWeekAssignment, UnavailabilityRequest
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
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
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
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: str
    warnings: List[str] = []
    bumped: List[str] = []   # Names of auto-generated assignments removed to make room


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

    # Alias Faculty a second time for the creator join
    CreatorFaculty = aliased(Faculty, flat=True)

    # Single query — joins block → subject faculty, service week, and creator
    # using specific column selection to avoid touching any unmigrated columns
    blocks = db.query(
        FacultyBlock.id,
        FacultyBlock.faculty_id,
        Faculty.name.label('faculty_name'),
        FacultyBlock.week_id,
        ServiceWeek.label.label('week_label'),
        FacultyBlock.reason,
        FacultyBlock.created_by,
        CreatorFaculty.name.label('created_by_name'),
        FacultyBlock.created_at
    ).join(
        Faculty, FacultyBlock.faculty_id == Faculty.id
    ).join(
        ServiceWeek, FacultyBlock.week_id == ServiceWeek.id
    ).outerjoin(
        CreatorFaculty, FacultyBlock.created_by == CreatorFaculty.id
    ).filter(
        ServiceWeek.year == year
    ).order_by(
        ServiceWeek.week_number
    ).all()

    return [
        BlockResponse(
            id=block.id,
            faculty_id=block.faculty_id,
            faculty_name=block.faculty_name,
            week_id=block.week_id,
            week_label=block.week_label,
            reason=block.reason or "",
            created_by=block.created_by,
            created_by_name=block.created_by_name,
            created_at=block.created_at.isoformat() if block.created_at else datetime.utcnow().isoformat()
        )
        for block in blocks
    ]


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

    CreatorFaculty = aliased(Faculty, flat=True)

    assignments = db.query(
        ServiceWeekAssignment.id,
        ServiceWeekAssignment.faculty_id,
        Faculty.name.label('faculty_name'),
        ServiceWeekAssignment.week_id,
        ServiceWeek.label.label('week_label'),
        ServiceWeekAssignment.service_type,
        ServiceWeekAssignment.reason,
        ServiceWeekAssignment.created_by,
        CreatorFaculty.name.label('created_by_name'),
        ServiceWeekAssignment.created_at
    ).join(
        Faculty, ServiceWeekAssignment.faculty_id == Faculty.id
    ).join(
        ServiceWeek, ServiceWeekAssignment.week_id == ServiceWeek.id
    ).outerjoin(
        CreatorFaculty, ServiceWeekAssignment.created_by == CreatorFaculty.id
    ).filter(
        and_(
            ServiceWeek.year == year,
            ServiceWeekAssignment.is_manual == True
        )
    ).order_by(
        ServiceWeek.week_number
    ).all()

    return [
        AssignmentResponse(
            id=a.id,
            faculty_id=a.faculty_id,
            faculty_name=a.faculty_name,
            week_id=a.week_id,
            week_label=a.week_label,
            service_type=a.service_type,
            reason=a.reason or "",
            created_by=a.created_by,
            created_by_name=a.created_by_name,
            created_at=a.created_at.isoformat() if a.created_at else datetime.utcnow().isoformat()
        )
        for a in assignments
    ]


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
    valid_services = ['MICU', 'APP-ICU', 'Procedures', 'Consults', 'Backup']
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

    # Check for unavailability conflicts and build warnings list
    warnings = []
    conflict = db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.faculty_id == request.faculty_id,
        UnavailabilityRequest.week_id == request.week_id,
        UnavailabilityRequest.status == "unavailable"
    ).first()
    if conflict:
        warnings.append(
            f"{faculty.name} has submitted an unavailability request for {week.label}. "
            f"This manual assignment overrides it."
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

    # ── Rebalance: if this service/week is now over the required slot count,
    # bump auto-generated assignments (is_manual=False, imported=False) to
    # make room.  Manual and imported assignments are never auto-removed. ──────
    from backend.schedule_generator import SERVICE_REQUIREMENTS
    required_slots = SERVICE_REQUIREMENTS.get(request.service_type, 1)

    all_for_slot = db.query(ServiceWeekAssignment).filter(
        ServiceWeekAssignment.week_id == request.week_id,
        ServiceWeekAssignment.service_type == request.service_type
    ).all()

    bumped = []
    overfill = len(all_for_slot) - required_slots
    if overfill > 0:
        # Find auto-generated candidates to bump (oldest first so newest manual wins)
        auto_generated = [
            a for a in all_for_slot
            if not a.is_manual and not a.imported
        ]
        # Sort by created_at ascending so we bump the earliest auto-assignment first
        auto_generated.sort(key=lambda a: a.created_at or datetime.utcnow())
        to_remove = auto_generated[:overfill]
        faculty_lookup = {f.id: f.name for f in db.query(Faculty).all()}
        for a in to_remove:
            bumped_name = faculty_lookup.get(a.faculty_id, a.faculty_id)
            bumped.append(bumped_name)
            db.delete(a)
        db.commit()

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
        created_at=assignment.created_at.isoformat(),
        warnings=warnings,
        bumped=bumped
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


# ==================== SLEEP SCHEDULE CSV IMPORT ====================

SLEEP_REASON = "Sleep schedule"


@router.post("/import-sleep-csv")
async def import_sleep_schedule_csv(
    file: UploadFile = File(...),
    clear_existing: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """
    Import a sleep-schedule CSV as FacultyBlock records.

    CSV format:
        Start Day,FACULTY_ID1,FACULTY_ID2,...
        MM/DD/YY,0,1,0,...

    A value of 1 means that faculty member is blocked from service
    assignments that week due to sleep schedule.

    Query params:
        clear_existing (bool): If true, delete all existing "Sleep schedule"
                               blocks for the faculty in the CSV before importing.
    """

    # ── 1. Read and parse the CSV ────────────────────────────────────────────
    contents = await file.read()
    text = contents.decode("utf-8-sig")  # handle BOM if present
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames

    if not headers or len(headers) < 2:
        raise HTTPException(
            status_code=400,
            detail="CSV must have at least two columns: 'Start Day' plus one faculty ID column."
        )

    faculty_id_cols = [h.strip() for h in headers[1:]]

    rows = []
    bad_dates = []
    for raw in reader:
        start_raw = raw.get(headers[0], "").strip()
        if not start_raw:
            continue
        try:
            start_date = datetime.strptime(start_raw, "%m/%d/%y").date()
        except ValueError:
            bad_dates.append(start_raw)
            continue
        blocked = {fid: (raw.get(fid, "0").strip() == "1") for fid in faculty_id_cols}
        rows.append({"start_date": start_date, "blocked": blocked})

    # ── 2. Validate faculty IDs ──────────────────────────────────────────────
    faculty_map = {}
    unknown_ids = []
    for fid in faculty_id_cols:
        f = db.query(Faculty).filter(Faculty.id == fid).first()
        if f:
            faculty_map[fid] = f
        else:
            unknown_ids.append(fid)

    if not faculty_map:
        raise HTTPException(
            status_code=400,
            detail=(
                f"None of the faculty IDs in the CSV header ({faculty_id_cols}) "
                f"were found in the database."
            )
        )

    # ── 3. Optionally clear existing sleep blocks ────────────────────────────
    cleared = 0
    if clear_existing:
        for fid in faculty_map:
            blocks = db.query(FacultyBlock).filter(
                FacultyBlock.faculty_id == fid,
                FacultyBlock.reason == SLEEP_REASON
            ).all()
            for b in blocks:
                db.delete(b)
                cleared += 1
        db.commit()

    # ── 4. Build start_date → ServiceWeek lookup ─────────────────────────────
    date_strings = list({r["start_date"].isoformat() for r in rows})
    sw_by_date = {}
    for ds in date_strings:
        sw = db.query(ServiceWeek).filter(ServiceWeek.start_date == ds).first()
        if sw:
            sw_by_date[ds] = sw

    # ── 5. Create FacultyBlock records ───────────────────────────────────────
    created = 0
    skipped_duplicate = 0
    skipped_no_week = []

    for row in rows:
        ds = row["start_date"].isoformat()
        sw = sw_by_date.get(ds)
        if sw is None:
            skipped_no_week.append(ds)
            continue

        for fid, is_blocked in row["blocked"].items():
            if fid not in faculty_map or not is_blocked:
                continue

            existing = db.query(FacultyBlock).filter(
                and_(
                    FacultyBlock.faculty_id == fid,
                    FacultyBlock.week_id == sw.id
                )
            ).first()

            if existing:
                skipped_duplicate += 1
                continue

            block = FacultyBlock(
                id=str(uuid.uuid4()),
                faculty_id=fid,
                week_id=sw.id,
                reason=SLEEP_REASON,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            )
            db.add(block)
            created += 1

    db.commit()

    return {
        "success": True,
        "blocks_created": created,
        "blocks_cleared": cleared,
        "skipped_duplicate": skipped_duplicate,
        "skipped_no_matching_week": list(set(skipped_no_week)),
        "unknown_faculty_ids": unknown_ids,
        "bad_dates": bad_dates,
        "message": (
            f"Import complete. {created} sleep block(s) created"
            + (f", {cleared} existing block(s) cleared" if cleared else "")
            + (f". Unknown faculty IDs ignored: {unknown_ids}" if unknown_ids else "")
            + "."
        )
    }
