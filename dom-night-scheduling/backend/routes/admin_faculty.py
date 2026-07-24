"""
Admin endpoints for faculty/provider management — DOM Hospitalist Nights.

Trimmed from FacultyHubAdaptable's admin_faculty.py: drops the weekly
service-block (ServiceWeek / ServiceWeekAssignment) endpoints entirely since
this instance is shift_based / night-only. `service_week_counts` is kept as
an always-empty dict in the response so the shared faculty-management UI
module continues to work unmodified.

Group-specific attributes (e.g. which night lanes a provider is qualified
for) live in Faculty.extra_config (JSON), defined via instance_config
faculty_attributes.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
import json

from backend.models import Faculty, get_db
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _faculty_response(faculty: Faculty) -> FacultyResponse:
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
        service_week_counts={},
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
    return [_faculty_response(f) for f in query.order_by(Faculty.name).all()]


@router.get("/faculty/stats/summary")
def get_faculty_stats(
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total  = db.query(func.count(Faculty.id)).scalar()
    active = db.query(func.count(Faculty.id)).filter_by(active=True).scalar()
    admins = db.query(func.count(Faculty.id)).filter_by(is_admin=True).scalar()
    return {
        "total_faculty":    total,
        "active_faculty":   active,
        "admin_count":      admins,
        "inactive_faculty": total - active,
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
    return _faculty_response(faculty)


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
    return _faculty_response(new_faculty)


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
    return _faculty_response(faculty)


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
    return _faculty_response(faculty)


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
    return _faculty_response(faculty)


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
