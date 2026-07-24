"""
Admin endpoints for faculty/provider management.
All PCCM-specific fields (rank, clinical_effort_pct, base_points, etc.) have been
removed.  Group-specific attributes live in Faculty.extra_config (JSON) and are
defined via instance_config faculty_attributes.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
from datetime import datetime
import uuid
import json

from backend.models import Faculty, ServiceWeekAssignment, ServiceWeek, UnavailabilityRequest, get_db
from backend.auth import require_admin, hash_password, create_session

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ==========================================
# PYDANTIC MODELS
# ==========================================

class FacultyCreate(BaseModel):
    id: str
    name: str
    email: EmailStr
    active: bool = True
    is_admin: bool = False
    moonlighter: bool = False
    draft_exempt: bool = False
    moonlighting_priority: int = 2
    extra_config: Dict[str, Any] = {}


class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    active: Optional[bool] = None
    is_admin: Optional[bool] = None
    moonlighter: Optional[bool] = None
    draft_exempt: Optional[bool] = None
    moonlighting_priority: Optional[int] = None
    extra_config: Optional[Dict[str, Any]] = None


class FacultyResponse(BaseModel):
    id: str
    name: str
    email: str
    active: bool
    is_admin: bool
    password_changed: bool
    registered: bool
    moonlighter: bool
    draft_exempt: bool
    moonlighting_priority: int
    extra_config: Dict[str, Any]
    service_week_counts: Dict[str, int]


class FacultyStatusUpdate(BaseModel):
    active: Optional[bool] = None
    is_active: Optional[bool] = None


class ServiceWeekAssignmentDetail(BaseModel):
    assignment_id: str
    week_id: str
    week_number: int
    week_label: str
    start_date: str
    end_date: str
    service_type: str
    week_type: str
    assigned_at: Optional[str] = None


class ServiceWeekAssignmentRequest(BaseModel):
    week_id: str
    service_type: str
    notes: Optional[str] = None


class ServiceWeekReassignRequest(BaseModel):
    from_faculty_id: str
    to_faculty_id: str
    week_id: str
    service_type: str
    notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _service_week_counts(faculty_id: str, db: Session) -> Dict[str, int]:
    rows = db.query(
        ServiceWeekAssignment.service_type,
        func.count(ServiceWeekAssignment.id).label("count"),
    ).filter(ServiceWeekAssignment.faculty_id == faculty_id
    ).group_by(ServiceWeekAssignment.service_type).all()
    return {row.service_type: row.count for row in rows}


def _faculty_response(faculty: Faculty, db: Session) -> FacultyResponse:
    try:
        extra = json.loads(faculty.extra_config or "{}")
    except (json.JSONDecodeError, TypeError):
        extra = {}
    return FacultyResponse(
        id=faculty.id,
        name=faculty.name,
        email=faculty.email,
        active=faculty.active,
        is_admin=faculty.is_admin,
        password_changed=faculty.password_changed,
        registered=faculty.registered,
        moonlighter=faculty.moonlighter,
        draft_exempt=faculty.draft_exempt or False,
        moonlighting_priority=faculty.moonlighting_priority or 2,
        extra_config=extra,
        service_week_counts=_service_week_counts(faculty.id, db),
    )


# ==========================================
# FACULTY CRUD
# ==========================================

@router.get("/faculty", response_model=List[FacultyResponse])
def list_faculty(
    active_only: bool = False,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Faculty)
    if active_only:
        query = query.filter_by(active=True)
    return [_faculty_response(f, db) for f in query.order_by(Faculty.name).all()]


@router.get("/faculty/stats/summary")
def get_faculty_stats(
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total        = db.query(func.count(Faculty.id)).scalar()
    active       = db.query(func.count(Faculty.id)).filter_by(active=True).scalar()
    admins       = db.query(func.count(Faculty.id)).filter_by(is_admin=True).scalar()
    moonlighters = db.query(func.count(Faculty.id)).filter_by(moonlighter=True).scalar()
    return {
        "total_faculty":     total,
        "active_faculty":    active,
        "admin_count":       admins,
        "moonlighter_count": moonlighters,
        "inactive_faculty":  total - active,
    }


@router.get("/faculty/{faculty_id}", response_model=FacultyResponse)
def get_faculty(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return _faculty_response(faculty, db)


@router.post("/faculty", response_model=FacultyResponse, status_code=201)
def create_faculty(
    faculty_data: FacultyCreate,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Faculty).filter(Faculty.id.ilike(faculty_data.id)).first():
        raise HTTPException(status_code=400,
            detail=f"Provider ID '{faculty_data.id}' already exists.")
    if faculty_data.email:
        existing = db.query(Faculty).filter(Faculty.email.ilike(faculty_data.email)).first()
        if existing:
            raise HTTPException(status_code=400,
                detail=f"Email '{faculty_data.email}' already in use (ID: {existing.id}).")

    new_faculty = Faculty(
        id=faculty_data.id,
        name=faculty_data.name,
        email=faculty_data.email,
        active=faculty_data.active,
        is_admin=faculty_data.is_admin,
        moonlighter=faculty_data.moonlighter,
        draft_exempt=faculty_data.draft_exempt,
        moonlighting_priority=faculty_data.moonlighting_priority,
        extra_config=json.dumps(faculty_data.extra_config),
        password_hash=hash_password("ChangeMe123!"),
        password_changed=False,
        registered=False,
    )
    db.add(new_faculty)
    db.commit()
    db.refresh(new_faculty)
    return _faculty_response(new_faculty, db)


@router.patch("/faculty/{faculty_id}", response_model=FacultyResponse)
def update_faculty(
    faculty_id: str,
    faculty_data: FacultyUpdate,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    update_data = faculty_data.dict(exclude_unset=True)

    if "email" in update_data and update_data["email"]:
        existing = db.query(Faculty).filter(
            Faculty.email.ilike(update_data["email"]),
            Faculty.id != faculty_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400,
                detail=f"Email '{update_data['email']}' already in use (ID: {existing.id}).")

    # Merge extra_config rather than replace
    if "extra_config" in update_data:
        try:
            current = json.loads(faculty.extra_config or "{}")
        except (json.JSONDecodeError, TypeError):
            current = {}
        current.update(update_data.pop("extra_config"))
        faculty.extra_config = json.dumps(current)

    for field, value in update_data.items():
        setattr(faculty, field, value)

    db.commit()
    db.refresh(faculty)
    return _faculty_response(faculty, db)


@router.put("/faculty/{faculty_id}/status")
def update_faculty_status(
    faculty_id: str,
    payload: FacultyStatusUpdate,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    new_active = payload.active if payload.active is not None else payload.is_active
    if new_active is None:
        raise HTTPException(status_code=400, detail="Body must include 'active' or 'is_active'.")
    faculty.active = bool(new_active)
    db.commit()
    return {"id": faculty.id, "name": faculty.name, "active": faculty.active}


@router.delete("/faculty/{faculty_id}", status_code=204)
def delete_faculty(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    faculty.active = False
    db.commit()
    return Response(status_code=204)


@router.post("/faculty/{faculty_id}/reset-password")
def reset_faculty_password(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    default_password = "ChangeMe123!"
    faculty.password_hash = hash_password(default_password)
    faculty.password_changed = False
    db.commit()
    return {"success": True, "faculty_id": faculty_id,
            "default_password": default_password,
            "message": f"Password reset for {faculty.name}"}


@router.post("/faculty/{faculty_id}/toggle-admin", response_model=FacultyResponse)
def toggle_admin_status(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    faculty.is_admin = not faculty.is_admin
    db.commit()
    db.refresh(faculty)
    return _faculty_response(faculty, db)


@router.post("/faculty/{faculty_id}/toggle-draft-exempt", response_model=FacultyResponse)
def toggle_draft_exempt(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    faculty.draft_exempt = not (faculty.draft_exempt or False)
    db.commit()
    db.refresh(faculty)
    return _faculty_response(faculty, db)


# ==========================================
# IMPERSONATION
# ==========================================

@router.post("/impersonate/{faculty_id}")
async def impersonate_faculty(
    faculty_id: str,
    request: Request,
    response: Response,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(Faculty).filter_by(id=faculty_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Faculty not found")
    token = create_session(target.id, target.name, target.is_admin,
                           impersonated_by=admin_user.id, db=db)
    response.set_cookie(key="session_token", value=token, httponly=True,
                        samesite="lax", max_age=14 * 24 * 3600)
    return {"success": True, "impersonating": target.name, "faculty_id": target.id}


@router.post("/return-to-admin")
async def return_to_admin(
    admin_faculty_id: str,
    request: Request,
    response: Response,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    admin_faculty = db.query(Faculty).filter_by(id=admin_faculty_id, is_admin=True).first()
    if not admin_faculty:
        raise HTTPException(status_code=403, detail="Invalid admin account")
    token = create_session(admin_faculty.id, admin_faculty.name, admin_faculty.is_admin, db=db)
    response.set_cookie(key="session_token", value=token, httponly=True,
                        samesite="lax", max_age=14 * 24 * 3600)
    return {"success": True, "message": f"Returned to admin: {admin_faculty.name}"}


# ==========================================
# RESET ENDPOINTS
# ==========================================

@router.post("/reset/requests")
def reset_all_requests(
    year: Optional[int] = None,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if year:
        week_ids = [w.id for w in db.query(ServiceWeek).filter_by(year=year).all()]
        deleted = db.query(UnavailabilityRequest).filter(
            UnavailabilityRequest.week_id.in_(week_ids)
        ).delete(synchronize_session=False)
    else:
        deleted = db.query(UnavailabilityRequest).delete(synchronize_session=False)
    db.commit()
    return {"success": True, "requests_deleted": deleted, "year": year or "all"}


# ==========================================
# SERVICE WEEK ASSIGNMENT ENDPOINTS
# ==========================================

@router.get("/faculty/{faculty_id}/service-weeks",
            response_model=List[ServiceWeekAssignmentDetail])
def get_faculty_service_weeks(
    faculty_id: str,
    year: Optional[int] = None,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    query = db.query(ServiceWeekAssignment, ServiceWeek).join(
        ServiceWeek, ServiceWeekAssignment.week_id == ServiceWeek.id
    ).filter(ServiceWeekAssignment.faculty_id == faculty_id)
    if year:
        query = query.filter(ServiceWeek.year == year)
    return [
        ServiceWeekAssignmentDetail(
            assignment_id=a.id, week_id=w.id, week_number=w.week_number,
            week_label=w.label, start_date=w.start_date.isoformat(),
            end_date=w.end_date.isoformat(), service_type=a.service_type,
            week_type=w.week_type,
            assigned_at=a.created_at.isoformat() if a.created_at else None,
        )
        for a, w in query.order_by(ServiceWeek.week_number).all()
    ]


@router.post("/faculty/{faculty_id}/service-weeks/assign")
def assign_service_week(
    faculty_id: str,
    assignment_data: ServiceWeekAssignmentRequest,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    week = db.query(ServiceWeek).filter_by(id=assignment_data.week_id).first()
    if not week:
        raise HTTPException(status_code=404, detail="Service week not found")
    if db.query(ServiceWeekAssignment).filter_by(
        faculty_id=faculty_id, week_id=assignment_data.week_id,
        service_type=assignment_data.service_type,
    ).first():
        raise HTTPException(status_code=400, detail="Week already assigned for this service type")
    new_a = ServiceWeekAssignment(
        id=str(uuid.uuid4()), faculty_id=faculty_id,
        week_id=assignment_data.week_id, service_type=assignment_data.service_type,
        created_at=datetime.utcnow(), imported=False,
    )
    db.add(new_a)
    db.commit()
    return {"success": True, "assignment_id": new_a.id,
            "week_number": week.week_number, "service_type": assignment_data.service_type}


@router.delete("/faculty/{faculty_id}/service-weeks/{assignment_id}")
def unassign_service_week(
    faculty_id: str, assignment_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    a = db.query(ServiceWeekAssignment).filter_by(
        id=assignment_id, faculty_id=faculty_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()
    return {"success": True, "assignment_id": assignment_id}


@router.put("/faculty/service-weeks/reassign")
def reassign_service_week(
    reassign_data: ServiceWeekReassignRequest,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from_f = db.query(Faculty).filter_by(id=reassign_data.from_faculty_id).first()
    to_f   = db.query(Faculty).filter_by(id=reassign_data.to_faculty_id).first()
    if not from_f or not to_f:
        raise HTTPException(status_code=404, detail="Faculty not found")
    week = db.query(ServiceWeek).filter_by(id=reassign_data.week_id).first()
    if not week:
        raise HTTPException(status_code=404, detail="Service week not found")
    original = db.query(ServiceWeekAssignment).filter_by(
        faculty_id=reassign_data.from_faculty_id, week_id=reassign_data.week_id,
        service_type=reassign_data.service_type,
    ).first()
    if not original:
        raise HTTPException(status_code=404, detail="Original assignment not found")
    if db.query(ServiceWeekAssignment).filter_by(
        faculty_id=reassign_data.to_faculty_id, week_id=reassign_data.week_id,
        service_type=reassign_data.service_type,
    ).first():
        raise HTTPException(status_code=400, detail="Target faculty already assigned this week")
    db.delete(original)
    db.add(ServiceWeekAssignment(
        id=str(uuid.uuid4()), faculty_id=reassign_data.to_faculty_id,
        week_id=reassign_data.week_id, service_type=reassign_data.service_type,
        created_at=datetime.utcnow(), imported=False,
    ))
    db.commit()
    return {"success": True, "from": from_f.name, "to": to_f.name,
            "week_number": week.week_number, "service_type": reassign_data.service_type}
