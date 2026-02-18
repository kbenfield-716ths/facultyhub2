"""
Admin endpoints for faculty management.
These require admin authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime
import uuid

from backend.models import Faculty, ServiceWeekAssignment, ServiceWeek, UnavailabilityRequest, get_db
from backend.auth import require_admin, hash_password, create_session
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ==========================================
# PYDANTIC MODELS
# ==========================================

class FacultyCreate(BaseModel):
    """Model for creating new faculty"""
    id: str  # UVA computing ID
    name: str
    email: EmailStr
    rank: str  # assistant, associate, full
    clinical_effort_pct: int
    base_points: int
    bonus_points: int = 0
    active: bool = True
    is_admin: bool = False
    moonlighter: bool = False
    draft_exempt: bool = False
    micu_weeks: int = 0
    app_icu_weeks: int = 0
    procedure_weeks: int = 0
    consult_weeks: int = 0


class FacultyUpdate(BaseModel):
    """Model for updating existing faculty"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    rank: Optional[str] = None
    clinical_effort_pct: Optional[int] = None
    base_points: Optional[int] = None
    bonus_points: Optional[int] = None
    active: Optional[bool] = None
    is_admin: Optional[bool] = None
    moonlighter: Optional[bool] = None
    draft_exempt: Optional[bool] = None
    micu_weeks: Optional[int] = None
    app_icu_weeks: Optional[int] = None
    procedure_weeks: Optional[int] = None
    consult_weeks: Optional[int] = None


class ServiceAssignmentSummary(BaseModel):
    """Summary of service week assignments"""
    MICU: int = 0
    APP_ICU: int = 0
    Procedures: int = 0
    Consults: int = 0
    total: int = 0


class FacultyResponse(BaseModel):
    """Response model for faculty data"""
    id: str
    name: str
    email: str
    rank: str
    clinical_effort_pct: int
    base_points: int
    bonus_points: int
    total_points: int
    active: bool
    is_admin: bool
    password_changed: bool
    registered: bool
    moonlighter: bool
    draft_exempt: bool
    micu_weeks: int
    app_icu_weeks: int
    procedure_weeks: int
    consult_weeks: int
    service_weeks: ServiceAssignmentSummary


class ServiceWeekAssignmentDetail(BaseModel):
    """Detailed service week assignment"""
    assignment_id: str
    week_id: str
    week_number: int
    week_label: str
    start_date: str
    end_date: str
    service_type: str
    week_type: str
    status: str = "assigned"
    points_value: int
    assigned_at: Optional[str] = None
    notes: Optional[str] = None


class ServiceWeekAssignmentRequest(BaseModel):
    """Request to assign a service week"""
    week_id: str
    service_type: str
    notes: Optional[str] = None
    override_points: Optional[int] = None


class ServiceWeekReassignRequest(BaseModel):
    """Request to reassign a week from one faculty to another"""
    from_faculty_id: str
    to_faculty_id: str
    week_id: str
    service_type: str
    notes: Optional[str] = None


# ==========================================
# FACULTY CRUD ENDPOINTS
# ==========================================

@router.get("/faculty", response_model=List[FacultyResponse])
def list_faculty(
    active_only: bool = False,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get all faculty members with their service assignment summaries.
    Requires admin authentication.
    """
    query = db.query(Faculty)
    if active_only:
        query = query.filter_by(active=True)

    faculty_list = query.order_by(Faculty.name).all()

    result = []
    for faculty in faculty_list:
        # Count service assignments by type
        assignments = db.query(
            ServiceWeekAssignment.service_type,
            func.count(ServiceWeekAssignment.id).label('count')
        ).filter(
            ServiceWeekAssignment.faculty_id == faculty.id
        ).group_by(ServiceWeekAssignment.service_type).all()

        # Build service summary
        service_weeks = ServiceAssignmentSummary()
        total = 0
        for service_type, count in assignments:
            total += count
            if service_type == "MICU":
                service_weeks.MICU = count
            elif service_type == "APP-ICU":
                service_weeks.APP_ICU = count
            elif service_type == "Procedures":
                service_weeks.Procedures = count
            elif service_type == "Consults":
                service_weeks.Consults = count

        service_weeks.total = total

        result.append(FacultyResponse(
            id=faculty.id,
            name=faculty.name,
            email=faculty.email,
            rank=faculty.rank,
            clinical_effort_pct=faculty.clinical_effort_pct,
            base_points=faculty.base_points,
            bonus_points=faculty.bonus_points,
            total_points=faculty.base_points + faculty.bonus_points,
            active=faculty.active,
            is_admin=faculty.is_admin,
            password_changed=faculty.password_changed,
            registered=faculty.registered,
            moonlighter=faculty.moonlighter,
            draft_exempt=faculty.draft_exempt or False,
            micu_weeks=faculty.micu_weeks,
            app_icu_weeks=faculty.app_icu_weeks,
            procedure_weeks=faculty.procedure_weeks,
            consult_weeks=faculty.consult_weeks,
            service_weeks=service_weeks
        ))

    return result


@router.get("/faculty/{faculty_id}", response_model=FacultyResponse)
def get_faculty(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get a specific faculty member by ID with their service assignments.
    Requires admin authentication.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Count service assignments by type
    assignments = db.query(
        ServiceWeekAssignment.service_type,
        func.count(ServiceWeekAssignment.id).label('count')
    ).filter(
        ServiceWeekAssignment.faculty_id == faculty.id
    ).group_by(ServiceWeekAssignment.service_type).all()

    # Build service summary
    service_weeks = ServiceAssignmentSummary()
    total = 0
    for service_type, count in assignments:
        total += count
        if service_type == "MICU":
            service_weeks.MICU = count
        elif service_type == "APP-ICU":
            service_weeks.APP_ICU = count
        elif service_type == "Procedures":
            service_weeks.Procedures = count
        elif service_type == "Consults":
            service_weeks.Consults = count

    service_weeks.total = total

    return FacultyResponse(
        id=faculty.id,
        name=faculty.name,
        email=faculty.email,
        rank=faculty.rank,
        clinical_effort_pct=faculty.clinical_effort_pct,
        base_points=faculty.base_points,
        bonus_points=faculty.bonus_points,
        total_points=faculty.base_points + faculty.bonus_points,
        active=faculty.active,
        is_admin=faculty.is_admin,
        password_changed=faculty.password_changed,
        registered=faculty.registered,
        moonlighter=faculty.moonlighter,
        draft_exempt=faculty.draft_exempt or False,
        micu_weeks=faculty.micu_weeks,
        app_icu_weeks=faculty.app_icu_weeks,
        procedure_weeks=faculty.procedure_weeks,
        consult_weeks=faculty.consult_weeks,
        service_weeks=service_weeks
    )


@router.post("/faculty", response_model=FacultyResponse, status_code=status.HTTP_201_CREATED)
def create_faculty(
    faculty_data: FacultyCreate,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new faculty member.
    Requires admin authentication.
    """
    # Check if faculty ID already exists (case-insensitive)
    existing_id = db.query(Faculty).filter(
        Faculty.id.ilike(faculty_data.id)
    ).first()
    if existing_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Faculty with ID '{faculty_data.id}' already exists. Please use a different ID."
        )

    # Check if email already exists (if email is provided)
    if faculty_data.email:
        existing_email = db.query(Faculty).filter(
            Faculty.email.ilike(faculty_data.email)
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A faculty member with email '{faculty_data.email}' already exists (ID: {existing_email.id}). Please use a different email or update the existing faculty member."
            )

    # Create faculty with default password "PCCM2025!"
    default_password = "PCCM2025!"
    hashed_password = hash_password(default_password)

    new_faculty = Faculty(
        id=faculty_data.id,
        name=faculty_data.name,
        email=faculty_data.email,
        rank=faculty_data.rank,
        clinical_effort_pct=faculty_data.clinical_effort_pct,
        base_points=faculty_data.base_points,
        bonus_points=faculty_data.bonus_points,
        active=faculty_data.active,
        is_admin=faculty_data.is_admin,
        moonlighter=faculty_data.moonlighter,
        draft_exempt=faculty_data.draft_exempt,
        micu_weeks=faculty_data.micu_weeks,
        app_icu_weeks=faculty_data.app_icu_weeks,
        procedure_weeks=faculty_data.procedure_weeks,
        consult_weeks=faculty_data.consult_weeks,
        password_hash=hashed_password,
        password_changed=False,
        registered=False
    )

    db.add(new_faculty)
    db.commit()
    db.refresh(new_faculty)

    return FacultyResponse(
        id=new_faculty.id,
        name=new_faculty.name,
        email=new_faculty.email,
        rank=new_faculty.rank,
        clinical_effort_pct=new_faculty.clinical_effort_pct,
        base_points=new_faculty.base_points,
        bonus_points=new_faculty.bonus_points,
        total_points=new_faculty.base_points + new_faculty.bonus_points,
        active=new_faculty.active,
        is_admin=new_faculty.is_admin,
        password_changed=new_faculty.password_changed,
        registered=new_faculty.registered,
        moonlighter=new_faculty.moonlighter,
        draft_exempt=new_faculty.draft_exempt,
        micu_weeks=new_faculty.micu_weeks,
        app_icu_weeks=new_faculty.app_icu_weeks,
        procedure_weeks=new_faculty.procedure_weeks,
        consult_weeks=new_faculty.consult_weeks,
        service_weeks=ServiceAssignmentSummary()
    )


@router.patch("/faculty/{faculty_id}", response_model=FacultyResponse)
def update_faculty(
    faculty_id: str,
    faculty_data: FacultyUpdate,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update an existing faculty member.
    Requires admin authentication.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # If updating email, check for duplicates
    update_data = faculty_data.dict(exclude_unset=True)
    if 'email' in update_data and update_data['email']:
        existing_email = db.query(Faculty).filter(
            Faculty.email.ilike(update_data['email']),
            Faculty.id != faculty_id  # Exclude current faculty member
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{update_data['email']}' is already in use by another faculty member (ID: {existing_email.id}). Please use a different email."
            )

    # Update provided fields
    for field, value in update_data.items():
        setattr(faculty, field, value)

    db.commit()
    db.refresh(faculty)

    # Get service assignment summary
    assignments = db.query(
        ServiceWeekAssignment.service_type,
        func.count(ServiceWeekAssignment.id).label('count')
    ).filter(
        ServiceWeekAssignment.faculty_id == faculty.id
    ).group_by(ServiceWeekAssignment.service_type).all()

    service_weeks = ServiceAssignmentSummary()
    total = 0
    for service_type, count in assignments:
        total += count
        if service_type == "MICU":
            service_weeks.MICU = count
        elif service_type == "APP-ICU":
            service_weeks.APP_ICU = count
        elif service_type == "Procedures":
            service_weeks.Procedures = count
        elif service_type == "Consults":
            service_weeks.Consults = count
    service_weeks.total = total

    return FacultyResponse(
        id=faculty.id,
        name=faculty.name,
        email=faculty.email,
        rank=faculty.rank,
        clinical_effort_pct=faculty.clinical_effort_pct,
        base_points=faculty.base_points,
        bonus_points=faculty.bonus_points,
        total_points=faculty.base_points + faculty.bonus_points,
        active=faculty.active,
        is_admin=faculty.is_admin,
        password_changed=faculty.password_changed,
        registered=faculty.registered,
        moonlighter=faculty.moonlighter,
        draft_exempt=faculty.draft_exempt or False,
        micu_weeks=faculty.micu_weeks,
        app_icu_weeks=faculty.app_icu_weeks,
        procedure_weeks=faculty.procedure_weeks,
        consult_weeks=faculty.consult_weeks,
        service_weeks=service_weeks
    )


@router.delete("/faculty/{faculty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faculty(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete (deactivate) a faculty member.
    Requires admin authentication.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Deactivate instead of actually deleting
    faculty.active = False
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/faculty/{faculty_id}/reset-password", status_code=status.HTTP_200_OK)
def reset_faculty_password(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reset a faculty member's password to default.
    Requires admin authentication.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Reset to default password
    default_password = "PCCM2025!"
    faculty.password_hash = hash_password(default_password)
    faculty.password_changed = False

    db.commit()

    return {
        "success": True,
        "faculty_id": faculty_id,
        "default_password": default_password,
        "message": f"Password reset for {faculty.name}"
    }


@router.post("/faculty/{faculty_id}/toggle-admin", response_model=FacultyResponse)
def toggle_admin_status(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Toggle admin status for a faculty member.
    Requires admin authentication.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Toggle admin status
    faculty.is_admin = not faculty.is_admin
    db.commit()
    db.refresh(faculty)

    # Get service assignment summary
    assignments = db.query(
        ServiceWeekAssignment.service_type,
        func.count(ServiceWeekAssignment.id).label('count')
    ).filter(
        ServiceWeekAssignment.faculty_id == faculty.id
    ).group_by(ServiceWeekAssignment.service_type).all()

    service_weeks = ServiceAssignmentSummary()
    total = 0
    for service_type, count in assignments:
        total += count
        if service_type == "MICU":
            service_weeks.MICU = count
        elif service_type == "APP-ICU":
            service_weeks.APP_ICU = count
        elif service_type == "Procedures":
            service_weeks.Procedures = count
        elif service_type == "Consults":
            service_weeks.Consults = count
    service_weeks.total = total

    return FacultyResponse(
        id=faculty.id,
        name=faculty.name,
        email=faculty.email,
        rank=faculty.rank,
        clinical_effort_pct=faculty.clinical_effort_pct,
        base_points=faculty.base_points,
        bonus_points=faculty.bonus_points,
        total_points=faculty.base_points + faculty.bonus_points,
        active=faculty.active,
        is_admin=faculty.is_admin,
        password_changed=faculty.password_changed,
        registered=faculty.registered,
        moonlighter=faculty.moonlighter,
        draft_exempt=faculty.draft_exempt or False,
        micu_weeks=faculty.micu_weeks,
        app_icu_weeks=faculty.app_icu_weeks,
        procedure_weeks=faculty.procedure_weeks,
        consult_weeks=faculty.consult_weeks,
        service_weeks=service_weeks
    )


@router.post("/faculty/{faculty_id}/toggle-draft-exempt", response_model=FacultyResponse)
def toggle_draft_exempt(
    faculty_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Toggle draft exempt status for a faculty member.
    Requires admin authentication.
    """
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Toggle draft exempt status
    faculty.draft_exempt = not (faculty.draft_exempt or False)
    db.commit()
    db.refresh(faculty)

    # Get service assignment summary
    assignments = db.query(
        ServiceWeekAssignment.service_type,
        func.count(ServiceWeekAssignment.id).label('count')
    ).filter(
        ServiceWeekAssignment.faculty_id == faculty.id
    ).group_by(ServiceWeekAssignment.service_type).all()

    service_weeks = ServiceAssignmentSummary()
    total = 0
    for service_type, count in assignments:
        total += count
        if service_type == "MICU":
            service_weeks.MICU = count
        elif service_type == "APP-ICU":
            service_weeks.APP_ICU = count
        elif service_type == "Procedures":
            service_weeks.Procedures = count
        elif service_type == "Consults":
            service_weeks.Consults = count
    service_weeks.total = total

    return FacultyResponse(
        id=faculty.id,
        name=faculty.name,
        email=faculty.email,
        rank=faculty.rank,
        clinical_effort_pct=faculty.clinical_effort_pct,
        base_points=faculty.base_points,
        bonus_points=faculty.bonus_points,
        total_points=faculty.base_points + faculty.bonus_points,
        active=faculty.active,
        is_admin=faculty.is_admin,
        password_changed=faculty.password_changed,
        registered=faculty.registered,
        moonlighter=faculty.moonlighter,
        draft_exempt=faculty.draft_exempt or False,
        micu_weeks=faculty.micu_weeks,
        app_icu_weeks=faculty.app_icu_weeks,
        procedure_weeks=faculty.procedure_weeks,
        consult_weeks=faculty.consult_weeks,
        service_weeks=service_weeks
    )


@router.get("/faculty/stats/summary")
def get_faculty_stats(
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics about faculty.
    Requires admin authentication.
    """
    total = db.query(func.count(Faculty.id)).scalar()
    active = db.query(func.count(Faculty.id)).filter_by(active=True).scalar()
    admins = db.query(func.count(Faculty.id)).filter_by(is_admin=True).scalar()
    moonlighters = db.query(func.count(Faculty.id)).filter_by(moonlighter=True).scalar()

    return {
        "total_faculty": total,
        "active_faculty": active,
        "admin_count": admins,
        "moonlighter_count": moonlighters,
        "inactive_faculty": total - active
    }


@router.post("/impersonate/{faculty_id}")
async def impersonate_faculty(
    faculty_id: str,
    request: Request,
    response: Response,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Impersonate a faculty member (login as them for testing).
    Creates a new session as the target faculty.
    Requires admin authentication.
    """
    # Get target faculty
    target_faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not target_faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Create session as target faculty
    session_token = create_session(target_faculty.id, target_faculty.name, target_faculty.is_admin, impersonated_by=admin_user.id, db=db)

    # Set session cookie – 14 days, matches SESSION_LIFETIME_DAYS in auth.py
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=14 * 24 * 3600  # 14 days
    )

    return {
        "success": True,
        "impersonating": target_faculty.name,
        "faculty_id": target_faculty.id,
        "message": f"Now logged in as {target_faculty.name}. You are no longer admin."
    }


@router.post("/return-to-admin")
async def return_to_admin(
    admin_faculty_id: str,
    request: Request,
    response: Response,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Return from impersonation to admin account.
    """
    # Verify the admin faculty exists and is admin
    admin_faculty = db.query(Faculty).filter_by(id=admin_faculty_id, is_admin=True).first()
    if not admin_faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin account"
        )

    # Create session as admin
    session_token = create_session(admin_faculty.id, admin_faculty.name, admin_faculty.is_admin, db=db)

    # Set session cookie – 14 days, matches SESSION_LIFETIME_DAYS in auth.py
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=14 * 24 * 3600  # 14 days
    )

    return {
        "success": True,
        "message": f"Returned to admin account: {admin_faculty.name}"
    }


@router.post("/reset/points")
def reset_all_points(
    year: Optional[int] = None,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reset all faculty bonus points to 0.
    """
    faculty_list = db.query(Faculty).filter_by(active=True).all()
    count = 0
    for faculty in faculty_list:
        faculty.bonus_points = 0
        count += 1

    db.commit()

    return {
        "success": True,
        "faculty_reset": count,
        "message": f"Bonus points reset for {count} active faculty"
    }


@router.post("/reset/requests")
def reset_all_requests(
    year: Optional[int] = None,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Clear all unavailability requests.
    """
    if year:
        week_ids = [w.id for w in db.query(ServiceWeek).filter_by(year=year).all()]
        deleted = db.query(UnavailabilityRequest).filter(
            UnavailabilityRequest.week_id.in_(week_ids)
        ).delete(synchronize_session=False)
    else:
        deleted = db.query(UnavailabilityRequest).delete(synchronize_session=False)

    db.commit()

    return {
        "success": True,
        "requests_deleted": deleted,
        "year": year or "all",
        "message": f"Deleted {deleted} unavailability requests"
    }


@router.post("/reset/all")
def reset_everything(
    year: Optional[int] = None,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Nuclear option: Reset all faculty points and clear all requests.
    """
    # Reset bonus points
    faculty_list = db.query(Faculty).filter_by(active=True).all()
    faculty_count = 0
    for faculty in faculty_list:
        faculty.bonus_points = 0
        faculty_count += 1

    # Clear requests
    if year:
        week_ids = [w.id for w in db.query(ServiceWeek).filter_by(year=year).all()]
        requests_deleted = db.query(UnavailabilityRequest).filter(
            UnavailabilityRequest.week_id.in_(week_ids)
        ).delete(synchronize_session=False)
    else:
        requests_deleted = db.query(UnavailabilityRequest).delete(synchronize_session=False)

    db.commit()

    return {
        "success": True,
        "faculty_reset": faculty_count,
        "requests_deleted": requests_deleted,
        "year": year or "all",
        "message": f"Complete reset: {faculty_count} faculty, {requests_deleted} requests cleared"
    }


# ==========================================
# SERVICE WEEK ASSIGNMENT ENDPOINTS (NEW)
# ==========================================

@router.get("/faculty/{faculty_id}/service-weeks", response_model=List[ServiceWeekAssignmentDetail])
def get_faculty_service_weeks(
    faculty_id: str,
    year: Optional[int] = 2026,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get detailed list of service week assignments for a specific faculty member.
    Returns week details with assignments.
    """
    # Verify faculty exists
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Get assignments with week details
    assignments = db.query(ServiceWeekAssignment, ServiceWeek).join(
        ServiceWeek, ServiceWeekAssignment.week_id == ServiceWeek.id
    ).filter(
        ServiceWeekAssignment.faculty_id == faculty_id,
        ServiceWeek.year == year
    ).order_by(ServiceWeek.week_number).all()

    result = []
    for assignment, week in assignments:
        result.append(ServiceWeekAssignmentDetail(
            assignment_id=assignment.id,
            week_id=week.id,
            week_number=week.week_number,
            week_label=week.label,
            start_date=week.start_date.isoformat(),
            end_date=week.end_date.isoformat(),
            service_type=assignment.service_type,
            week_type=week.week_type,
            status="assigned",
            points_value=week.point_reward_work,
            assigned_at=assignment.created_at.isoformat() if assignment.created_at else None,
            notes=None
        ))

    return result


@router.post("/faculty/{faculty_id}/service-weeks/assign")
def assign_service_week(
    faculty_id: str,
    assignment_data: ServiceWeekAssignmentRequest,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Assign a service week to a faculty member.
    """
    # Verify faculty exists
    faculty = db.query(Faculty).filter_by(id=faculty_id).first()
    if not faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Verify week exists
    week = db.query(ServiceWeek).filter_by(id=assignment_data.week_id).first()
    if not week:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service week not found"
        )

    # Check if already assigned
    existing = db.query(ServiceWeekAssignment).filter_by(
        faculty_id=faculty_id,
        week_id=assignment_data.week_id,
        service_type=assignment_data.service_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Week already assigned to this faculty for this service type"
        )

    # Create assignment
    new_assignment = ServiceWeekAssignment(
        id=str(uuid.uuid4()),
        faculty_id=faculty_id,
        week_id=assignment_data.week_id,
        service_type=assignment_data.service_type,
        created_at=datetime.utcnow(),
        imported=False
    )

    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)

    return {
        "success": True,
        "assignment_id": new_assignment.id,
        "faculty_id": faculty_id,
        "week_number": week.week_number,
        "service_type": assignment_data.service_type,
        "message": f"Assigned {week.label} ({assignment_data.service_type}) to {faculty.name}"
    }


@router.delete("/faculty/{faculty_id}/service-weeks/{assignment_id}")
def unassign_service_week(
    faculty_id: str,
    assignment_id: str,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Remove a service week assignment from a faculty member.
    """
    # Find assignment
    assignment = db.query(ServiceWeekAssignment).filter_by(
        id=assignment_id,
        faculty_id=faculty_id
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found"
        )

    # Get week info for response
    week = db.query(ServiceWeek).filter_by(id=assignment.week_id).first()

    # Delete assignment
    db.delete(assignment)
    db.commit()

    return {
        "success": True,
        "faculty_id": faculty_id,
        "week_number": week.week_number if week else None,
        "service_type": assignment.service_type,
        "message": f"Removed assignment"
    }


@router.put("/faculty/service-weeks/reassign")
def reassign_service_week(
    reassign_data: ServiceWeekReassignRequest,
    admin_user: Faculty = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reassign a service week from one faculty member to another.
    """
    # Verify both faculty exist
    from_faculty = db.query(Faculty).filter_by(id=reassign_data.from_faculty_id).first()
    to_faculty = db.query(Faculty).filter_by(id=reassign_data.to_faculty_id).first()

    if not from_faculty or not to_faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty not found"
        )

    # Verify week exists
    week = db.query(ServiceWeek).filter_by(id=reassign_data.week_id).first()
    if not week:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service week not found"
        )

    # Find original assignment
    original = db.query(ServiceWeekAssignment).filter_by(
        faculty_id=reassign_data.from_faculty_id,
        week_id=reassign_data.week_id,
        service_type=reassign_data.service_type
    ).first()

    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original assignment not found"
        )

    # Check if target already assigned
    existing = db.query(ServiceWeekAssignment).filter_by(
        faculty_id=reassign_data.to_faculty_id,
        week_id=reassign_data.week_id,
        service_type=reassign_data.service_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target faculty already assigned to this week"
        )

    # Delete original
    db.delete(original)

    # Create new assignment
    new_assignment = ServiceWeekAssignment(
        id=str(uuid.uuid4()),
        faculty_id=reassign_data.to_faculty_id,
        week_id=reassign_data.week_id,
        service_type=reassign_data.service_type,
        created_at=datetime.utcnow(),
        imported=False
    )

    db.add(new_assignment)
    db.commit()

    return {
        "success": True,
        "from_faculty": from_faculty.name,
        "to_faculty": to_faculty.name,
        "week_number": week.week_number,
        "service_type": reassign_data.service_type,
        "message": f"Reassigned {week.label} from {from_faculty.name} to {to_faculty.name}"
    }
