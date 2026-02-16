"""
Faculty service availability request endpoints.
These allow faculty to submit their unavailable/available weeks.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from pydantic import BaseModel
from datetime import datetime
import uuid

from backend.models import Faculty, ServiceWeek, UnavailabilityRequest, get_db
from backend.auth import get_current_user
from backend.email_service import send_unavailability_confirmation
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/service-requests", tags=["service-requests"])

# Constants
MAX_CAPACITY = 12  # Maximum faculty who can request unavailable for a week
MAX_VOLUNTEERS = 6  # Maximum faculty who can volunteer for a week

# ==========================================
# PYDANTIC MODELS
# ==========================================

class UnavailabilityRequestInput(BaseModel):
    """Model for a single availability request.

    Note: points_spent and points_earned are calculated server-side
    based on the week's configuration.
    """
    week_id: str
    status: str  # "unavailable" or "available"
    service_preference: str = None  # Optional preference for service type
    # These fields are accepted but recalculated server-side for security
    points_spent: int = 0
    points_earned: int = 0


class UnavailabilityRequestSubmit(BaseModel):
    """Model for submitting multiple requests"""
    requests: List[UnavailabilityRequestInput]


class UnavailabilityRequestResponse(BaseModel):
    """Model for availability request response"""
    id: str
    faculty_id: str
    faculty_name: str
    week_id: str
    week_number: int
    week_label: str
    status: str
    points_spent: int
    points_earned: int
    service_preference: str = None
    created_at: datetime

    class Config:
        from_attributes = True


# Dynamic pricing removed - using fixed costs per week configuration


# ==========================================
# ENDPOINTS
# ==========================================

@router.post("", status_code=status.HTTP_201_CREATED)
def submit_unavailability_requests(
    data: UnavailabilityRequestSubmit,
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit or update availability requests for the current faculty member.
    This replaces all existing requests for this faculty member.

    Points are calculated server-side based on week configuration (fixed costs).
    Enforces capacity limits: 12 unavailable, 6 volunteers per week.
    Enforces exclusivity: cannot be both unavailable AND volunteer for same week.
    """
    try:
        # VALIDATION 1: Check for exclusivity violation (same week appearing twice)
        week_ids_seen = set()
        for req in data.requests:
            if req.week_id in week_ids_seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot have multiple requests for the same week. Each week can only have one status (unavailable OR volunteer)."
                )
            week_ids_seen.add(req.week_id)

        # Delete existing requests for this faculty
        db.query(UnavailabilityRequest).filter(
            UnavailabilityRequest.faculty_id == current_user.id
        ).delete()
        db.flush()  # Ensure deletions are committed before counting

        # Track totals for validation
        total_points_spent = 0
        total_points_earned = 0

        # Create new requests
        created_requests = []
        for req in data.requests:
            # Verify week exists and get its point configuration
            week = db.query(ServiceWeek).filter_by(id=req.week_id).first()
            if not week:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Week {req.week_id} not found"
                )

            # Validate status
            if req.status not in ["unavailable", "available"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {req.status}. Must be 'unavailable' or 'available'"
                )

            # Check capacity based on request type
            if req.status == "unavailable":
                # Count current unavailable requests for this week (excluding current user)
                current_requests = db.query(func.count(UnavailabilityRequest.id)).filter(
                    UnavailabilityRequest.week_id == req.week_id,
                    UnavailabilityRequest.status == "unavailable"
                ).scalar() or 0

                # Enforce capacity limit
                if current_requests >= MAX_CAPACITY:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Week {week.week_number} ({week.label}) is full. Maximum {MAX_CAPACITY} faculty can request this week as unavailable."
                    )

                # Use fixed cost from week configuration
                points_spent = week.point_cost_off
                points_earned = 0

            else:  # available (volunteering)
                # Count current volunteers for this week (excluding current user)
                volunteer_count = db.query(func.count(UnavailabilityRequest.id)).filter(
                    UnavailabilityRequest.week_id == req.week_id,
                    UnavailabilityRequest.status == "available"
                ).scalar() or 0

                # Enforce volunteer capacity limit
                if volunteer_count >= MAX_VOLUNTEERS:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Week {week.week_number} ({week.label}) already has maximum volunteers. Maximum {MAX_VOLUNTEERS} faculty can volunteer for a week."
                    )

                points_spent = 0
                points_earned = week.point_reward_work

            total_points_spent += points_spent
            total_points_earned += points_earned

            # Create request with server-calculated points and service preference
            unavailability_request = UnavailabilityRequest(
                id=f"VR-{uuid.uuid4().hex[:8].upper()}",
                faculty_id=current_user.id,
                week_id=req.week_id,
                status=req.status,
                points_spent=points_spent,
                points_earned=points_earned,
                service_preference=req.service_preference,  # Save preference
                gives_priority=False  # Will be set by admin during draft
            )

            db.add(unavailability_request)
            created_requests.append(unavailability_request)
        
        # Validate faculty has enough points
        available_points = current_user.base_points + (current_user.bonus_points or 0)
        net_points = available_points - total_points_spent + total_points_earned
        
        if net_points < 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient points. You have {available_points} points but need {total_points_spent} for these requests."
            )
        
        db.commit()
        
        # Send confirmation email (non-blocking - errors won't fail the request)
        try:
            unavailable_weeks = []
            for req in created_requests:
                if req.status == "unavailable":
                    week = db.query(ServiceWeek).filter_by(id=req.week_id).first()
                    if week:
                        unavailable_weeks.append({
                            "week_number": week.week_number,
                            "start_date": week.start_date.isoformat(),
                            "end_date": week.end_date.isoformat()
                        })
            
            if unavailable_weeks:
                first_week = db.query(ServiceWeek).filter_by(
                    id=created_requests[0].week_id
                ).first()
                
                week_year = first_week.start_date.year
                week_month = first_week.start_date.month
                
                if week_month >= 7:
                    academic_year = f"{week_year}-{week_year+1}"
                else:
                    academic_year = f"{week_year-1}-{week_year}"
                
                send_unavailability_confirmation(
                    faculty_name=current_user.name,
                    faculty_email=current_user.email,
                    selected_weeks=unavailable_weeks,
                    academic_year=academic_year
                )
                logger.info(f"Unavailability confirmation email sent to {current_user.email}")
        except Exception as e:
            logger.error(f"Failed to send unavailability confirmation email: {e}")
        
        return {
            "message": f"Successfully submitted {len(created_requests)} requests",
            "total_requests": len(created_requests),
            "faculty_id": current_user.id,
            "faculty_name": current_user.name,
            "points_spent": total_points_spent,
            "points_earned": total_points_earned,
            "remaining_points": net_points
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit requests: {str(e)}"
        )


@router.get("/my-requests", response_model=List[UnavailabilityRequestResponse])
def get_my_requests(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all availability requests for the current faculty member.
    """
    requests = (
        db.query(
            UnavailabilityRequest.id,
            UnavailabilityRequest.faculty_id,
            Faculty.name.label("faculty_name"),
            UnavailabilityRequest.week_id,
            ServiceWeek.week_number,
            ServiceWeek.label.label("week_label"),
            UnavailabilityRequest.status,
            UnavailabilityRequest.points_spent,
            UnavailabilityRequest.points_earned,
            UnavailabilityRequest.service_preference,
            UnavailabilityRequest.created_at
        )
        .join(Faculty, UnavailabilityRequest.faculty_id == Faculty.id)
        .join(ServiceWeek, UnavailabilityRequest.week_id == ServiceWeek.id)
        .filter(UnavailabilityRequest.faculty_id == current_user.id)
        .order_by(ServiceWeek.week_number)
        .all()
    )

    return [
        UnavailabilityRequestResponse(
            id=r.id,
            faculty_id=r.faculty_id,
            faculty_name=r.faculty_name,
            week_id=r.week_id,
            week_number=r.week_number,
            week_label=r.week_label,
            status=r.status,
            points_spent=r.points_spent,
            points_earned=r.points_earned,
            service_preference=r.service_preference,
            created_at=r.created_at
        )
        for r in requests
    ]


@router.delete("/my-requests", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_requests(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete all availability requests for the current faculty member.
    """
    db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.faculty_id == current_user.id
    ).delete()
    
    db.commit()
    return None


@router.get("/summary")
def get_my_summary(
    current_user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics for the current faculty member.
    """
    # Count requests by status
    requests = db.query(UnavailabilityRequest).filter(
        UnavailabilityRequest.faculty_id == current_user.id
    ).all()
    
    unavailable_count = sum(1 for r in requests if r.status == "unavailable")
    available_count = sum(1 for r in requests if r.status == "available")
    
    total_spent = sum(r.points_spent for r in requests)
    total_earned = sum(r.points_earned for r in requests)
    
    base_points = current_user.base_points
    bonus_points = current_user.bonus_points or 0
    available_points = base_points + bonus_points - total_spent + total_earned
    
    return {
        "faculty_id": current_user.id,
        "faculty_name": current_user.name,
        "base_points": base_points,
        "bonus_points": bonus_points,
        "total_points": base_points + bonus_points,
        "points_spent": total_spent,
        "points_earned": total_earned,
        "available_points": available_points,
        "weeks_unavailable": unavailable_count,
        "weeks_available": available_count,
        "total_requests": len(requests)
    }
