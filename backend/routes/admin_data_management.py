from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from backend.models import get_db, Faculty, UnavailabilityRequest, ServiceWeek, Signup, Shift, Month
from backend.auth import require_admin

router = APIRouter(prefix="/api/admin/data-management", tags=["data-management"])

class DeleteRequestsPayload(BaseModel):
    request_ids: List[str]

class DeleteSignupsPayload(BaseModel):
    signup_ids: List[int]

@router.get("/unavailability-requests")
async def get_unavailability_requests(
    year: str = "all",
    faculty: str = "all",
    status: str = "all",
    date_range: str = "all",
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Get unavailability requests with filters"""
    query = db.query(
        UnavailabilityRequest.id,
        UnavailabilityRequest.faculty_id,
        Faculty.name.label('faculty_name'),
        UnavailabilityRequest.week_id,
        ServiceWeek.label.label('week_label'),
        ServiceWeek.week_number,
        UnavailabilityRequest.status,
        UnavailabilityRequest.points_spent,
        UnavailabilityRequest.points_earned,
        UnavailabilityRequest.created_at
    ).join(Faculty).join(ServiceWeek)

    # Apply filters
    if year != "all":
        query = query.filter(ServiceWeek.year == int(year))
    if faculty != "all":
        query = query.filter(Faculty.name == faculty)
    if status != "all":
        query = query.filter(UnavailabilityRequest.status == status)

    results = query.all()
    return [{
        'id': r.id,
        'faculty_id': r.faculty_id,
        'faculty_name': r.faculty_name,
        'week_id': r.week_id,
        'week_label': r.week_label,
        'week_number': r.week_number,
        'status': r.status,
        'points_spent': r.points_spent,
        'points_earned': r.points_earned,
        'created_at': r.created_at.isoformat()
    } for r in results]

@router.post("/delete-unavailability")
async def delete_unavailability(
    payload: DeleteRequestsPayload,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Delete unavailability requests"""
    deleted = db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.id.in_(payload.request_ids)
    ).delete(synchronize_session=False)

    db.commit()
    return {"deleted_count": deleted}

@router.get("/moonlighting-signups")
async def get_moonlighting_signups(
    month: str = "all",
    provider: str = "all",
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Get moonlighting signups with filters"""
    query = db.query(
        Signup.id,
        Signup.provider_id,
        Faculty.name.label('provider_name'),
        Shift.month_id,
        Month.year,
        Month.month,
        Signup.desired_nights,
        Signup.created_at
    ).join(Faculty, Signup.provider_id == Faculty.id, isouter=True
    ).join(Shift, Signup.shift_id == Shift.id
    ).join(Month, Shift.month_id == Month.id)

    # Apply filters
    if month != "all":
        query = query.filter(Month.id == int(month))
    if provider != "all":
        query = query.filter(Signup.provider_id == provider)

    results = query.all()
    return [{
        'id': r.id,
        'provider_id': r.provider_id,
        'provider_name': r.provider_name or 'Unknown',
        'month_id': r.month_id,
        'month_label': f"{r.year}-{r.month:02d}",
        'desired_nights': r.desired_nights,
        'locked_dates_count': 0,  # Calculate if needed
        'created_at': r.created_at.isoformat()
    } for r in results]

@router.post("/delete-moonlighting")
async def delete_moonlighting(
    payload: DeleteSignupsPayload,
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Delete moonlighting signups"""
    deleted = db.query(Signup).filter(
        Signup.id.in_(payload.signup_ids)
    ).delete(synchronize_session=False)

    db.commit()
    return {"deleted_count": deleted}
