"""
Public service weeks endpoints.
Allows any authenticated faculty to view available weeks with dynamic pricing.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from pydantic import BaseModel

from backend.models import ServiceWeek, UnavailabilityRequest, ServiceWeekAssignment, get_db
from backend.auth import get_current_user
from backend.models import Faculty

router = APIRouter(prefix="/api/service-weeks", tags=["service-weeks"])

# Capacity limits
MAX_CAPACITY = 12  # Maximum faculty who can request unavailable for a week
MAX_VOLUNTEERS = 6  # Maximum faculty who can volunteer for a week


class ServiceWeekPublicResponse(BaseModel):
    """Public view of service week - available to all faculty."""
    id: str
    week_number: int
    label: str
    start_date: str
    end_date: str
    week_type: str
    base_cost: int  # Base cost for requesting unavailable
    point_cost_off: int  # Cost for requesting unavailable (fixed, no dynamic pricing)
    point_reward_work: int
    min_staff_required: int
    year: int
    # Unavailable request capacity info
    request_count: int = 0
    max_capacity: int = MAX_CAPACITY
    is_full: bool = False
    demand_level: str = "low"  # low, medium, high, critical, full
    spots_remaining: int = MAX_CAPACITY
    # Volunteer capacity info
    volunteer_count: int = 0
    max_volunteers: int = MAX_VOLUNTEERS
    is_volunteer_full: bool = False
    volunteer_spots_remaining: int = MAX_VOLUNTEERS
    

@router.get("", response_model=List[ServiceWeekPublicResponse])
async def get_service_weeks(
    year: int = 2026,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all service availability weeks for a given year with fixed pricing.
    Available to any authenticated faculty member.
    """
    weeks = db.query(ServiceWeek).filter(ServiceWeek.year == year).order_by(ServiceWeek.week_number).all()

    # Get request counts for each week
    result = []
    for week in weeks:
        # Count unavailable requests
        request_count = db.query(func.count(UnavailabilityRequest.id)).filter(
            UnavailabilityRequest.week_id == week.id,
            UnavailabilityRequest.status == "unavailable"
        ).scalar() or 0

        # Count volunteer requests
        volunteer_count = db.query(func.count(UnavailabilityRequest.id)).filter(
            UnavailabilityRequest.week_id == week.id,
            UnavailabilityRequest.status == "available"
        ).scalar() or 0

        # Determine demand level for unavailable requests
        if request_count >= MAX_CAPACITY:
            demand_level = "full"
        elif request_count >= 10:
            demand_level = "critical"
        elif request_count >= 8:
            demand_level = "high"
        elif request_count >= 5:
            demand_level = "medium"
        else:
            demand_level = "low"

        spots_remaining = max(0, MAX_CAPACITY - request_count)
        is_full = request_count >= MAX_CAPACITY

        volunteer_spots_remaining = max(0, MAX_VOLUNTEERS - volunteer_count)
        is_volunteer_full = volunteer_count >= MAX_VOLUNTEERS

        result.append(ServiceWeekPublicResponse(
            id=week.id,
            week_number=week.week_number,
            label=week.label,
            start_date=week.start_date.isoformat(),
            end_date=week.end_date.isoformat(),
            week_type=week.week_type,
            base_cost=week.point_cost_off,
            point_cost_off=week.point_cost_off,  # Fixed cost, no dynamic pricing
            point_reward_work=week.point_reward_work,
            min_staff_required=week.min_staff_required,
            year=week.year,
            request_count=request_count,
            max_capacity=MAX_CAPACITY,
            is_full=is_full,
            demand_level=demand_level,
            spots_remaining=spots_remaining,
            volunteer_count=volunteer_count,
            max_volunteers=MAX_VOLUNTEERS,
            is_volunteer_full=is_volunteer_full,
            volunteer_spots_remaining=volunteer_spots_remaining
        ))

    return result
