from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from backend.models import get_db, Faculty, UnavailabilityRequest, ServiceWeek, Signup, Shift, Month, DraftWeekRequest, DraftWaveConfig
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
    """Get unavailability requests with filters — includes both direct submissions and wave draft submissions"""

    # ── 1. Direct UnavailabilityRequests ──────────────────────────────────────
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

    if year != "all":
        query = query.filter(ServiceWeek.year == int(year))
    if faculty != "all":
        query = query.filter(Faculty.name == faculty)
    if status != "all":
        query = query.filter(UnavailabilityRequest.status == status)

    direct_results = query.all()
    combined = [{
        'id': r.id,
        'faculty_id': r.faculty_id,
        'faculty_name': r.faculty_name,
        'week_id': r.week_id,
        'week_label': r.week_label,
        'week_number': r.week_number,
        'status': r.status,
        'points_spent': r.points_spent,
        'points_earned': r.points_earned,
        'created_at': r.created_at.isoformat(),
        'source': 'Direct'
    } for r in direct_results]

    # ── 2. Wave Draft Requests (DraftWeekRequest) ─────────────────────────────
    # Find relevant draft configs based on year filter
    draft_query = db.query(DraftWaveConfig).filter(
        DraftWaveConfig.status.in_(['active', 'closed'])
    )
    if year != "all":
        draft_query = draft_query.filter(DraftWaveConfig.year == int(year))
    draft_configs = draft_query.all()

    for config in draft_configs:
        dq = db.query(
            DraftWeekRequest.id,
            DraftWeekRequest.faculty_id,
            Faculty.name.label('faculty_name'),
            DraftWeekRequest.week_id,
            ServiceWeek.label.label('week_label'),
            ServiceWeek.week_number,
            DraftWeekRequest.request_type,
            DraftWeekRequest.submitted_at
        ).join(Faculty, DraftWeekRequest.faculty_id == Faculty.id
        ).join(ServiceWeek, DraftWeekRequest.week_id == ServiceWeek.id
        ).filter(DraftWeekRequest.config_id == config.id)

        if faculty != "all":
            dq = dq.filter(Faculty.name == faculty)

        # Map request_type to status for consistent display
        # 'unavailable' → 'unavailable', 'volunteer' → 'available'
        if status != "all":
            mapped_type = 'volunteer' if status == 'available' else status
            dq = dq.filter(DraftWeekRequest.request_type == mapped_type)

        for r in dq.all():
            mapped_status = 'available' if r.request_type == 'volunteer' else r.request_type
            combined.append({
                'id': r.id,
                'faculty_id': r.faculty_id,
                'faculty_name': r.faculty_name,
                'week_id': r.week_id,
                'week_label': r.week_label,
                'week_number': r.week_number,
                'status': mapped_status,
                'points_spent': 0,
                'points_earned': 0,
                'created_at': r.submitted_at.isoformat(),
                'source': 'Wave Draft'
            })

    # Sort combined by week_number, then faculty_name for a clean display
    combined.sort(key=lambda x: (x['week_number'], x['faculty_name']))
    return combined

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
    faculty_filter: str = "all",
    db: Session = Depends(get_db),
    current_user: Faculty = Depends(require_admin)
):
    """Get moonlighting signups with filters"""
    query = db.query(
        Signup.id,
        Signup.provider_id,
        Faculty.name.label('faculty_name'),
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
    if faculty_filter != "all":
        query = query.filter(Signup.provider_id == faculty_filter)

    results = query.all()
    return [{
        'id': r.id,
        'faculty_id': r.provider_id,
        'faculty_name': r.faculty_name or 'Unknown',
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
