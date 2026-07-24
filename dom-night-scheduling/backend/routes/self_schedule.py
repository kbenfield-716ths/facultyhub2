"""
Provider-facing self-scheduling — DOM Hospitalist Nights.

A provider opens a quarter that is "open_for_preferences" and sees one row
per night. Nights blocked by their existing (day) schedule are not
selectable. For every open night they may mark "preferred" or "can_work"
(or leave it blank). The admin's builder uses these marks, plus each
provider's quota, to fill the schedule.

  GET    /api/self-schedule/quarters
  GET    /api/self-schedule/quarters/{id}/grid
  GET    /api/self-schedule/quarters/{id}/summary
  POST   /api/self-schedule/quarters/{id}/preferences
  DELETE /api/self-schedule/quarters/{id}/preferences/{night_date}
  GET    /api/self-schedule/quarters/{id}/my-schedule
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models import (
    Faculty, Quarter, SchedulePeriod, PeriodAssignment,
    BlockedNight, NightPreference, ProviderNightQuota, get_db,
)
from backend.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/self-schedule", tags=["self-schedule"])


# ── Pydantic ──────────────────────────────────────────────────────────────────

class PreferenceSet(BaseModel):
    night_date: date
    preference: str  # "preferred" | "can_work"


VALID_PREFERENCES = {"preferred", "can_work"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_quarter_or_404(db: Session, quarter_id: str) -> Quarter:
    q = db.query(Quarter).filter_by(id=quarter_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quarter not found")
    return q


def _provider_lanes(faculty: Faculty):
    try:
        extra = json.loads(faculty.extra_config or "{}")
    except (json.JSONDecodeError, TypeError):
        extra = {}
    lanes = extra.get("lanes")
    if not lanes:
        return ["admitter", "nocturnist"]
    return lanes


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _window_open(q: Quarter) -> bool:
    if q.status != "open_for_preferences":
        return False
    if q.preference_deadline and datetime.utcnow() > q.preference_deadline:
        return False
    return True


# ── Quarter list ─────────────────────────────────────────────────────────────

@router.get("/quarters")
def list_quarters(
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Quarters relevant to the current user: open for preferences, currently
    being built, or published (so they can see their final schedule).
    """
    quarters = db.query(Quarter).filter(
        Quarter.status.in_(["open_for_preferences", "building", "published"])
    ).order_by(Quarter.start_date.desc()).all()

    return [
        {
            "id": q.id,
            "name": q.name,
            "start_date": q.start_date.isoformat(),
            "end_date": q.end_date.isoformat(),
            "status": q.status,
            "preference_deadline": q.preference_deadline.isoformat() if q.preference_deadline else None,
            "window_open": _window_open(q),
        }
        for q in quarters
    ]


# ── Self-scheduling grid ─────────────────────────────────────────────────────

@router.get("/quarters/{quarter_id}/grid")
def get_grid(
    quarter_id: str,
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    One row per night in the quarter, from this provider's perspective:
      - blocked: True if this provider cannot work this night (existing
        day schedule) — not selectable in the UI.
      - lanes: which lanes (admitter/nocturnist) this provider is qualified
        for and would be eligible to fill.
      - my_preference: "preferred" | "can_work" | None
      - my_assignment: lane this provider is assigned to, if the quarter has
        been built/published (None otherwise).
    """
    q = _get_quarter_or_404(db, quarter_id)
    my_lanes = _provider_lanes(user)

    blocked_dates = {
        b.night_date
        for b in db.query(BlockedNight).filter_by(quarter_id=quarter_id, provider_id=user.id).all()
    }
    prefs = {
        p.night_date: p.preference
        for p in db.query(NightPreference).filter_by(quarter_id=quarter_id, provider_id=user.id).all()
    }

    # This provider's assignments for the quarter (if built/published)
    my_assignments = {}
    periods = db.query(SchedulePeriod).filter_by(rotation_key=quarter_id).all()
    period_by_id = {p.id: p for p in periods}
    if periods:
        assigns = db.query(PeriodAssignment).filter(
            PeriodAssignment.period_id.in_(list(period_by_id.keys())),
            PeriodAssignment.provider_id == user.id,
        ).all()
        for a in assigns:
            per = period_by_id.get(a.period_id)
            if per:
                my_assignments[per.period_date] = per.shift_type

    days = []
    for d in _daterange(q.start_date, q.end_date):
        days.append({
            "date": d.isoformat(),
            "blocked": d in blocked_dates,
            "lanes": my_lanes,
            "my_preference": prefs.get(d),
            "my_assignment": my_assignments.get(d),
        })

    return {
        "quarter_id": q.id,
        "name": q.name,
        "status": q.status,
        "window_open": _window_open(q),
        "preference_deadline": q.preference_deadline.isoformat() if q.preference_deadline else None,
        "days": days,
    }


@router.get("/quarters/{quarter_id}/summary")
def get_summary(
    quarter_id: str,
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    override = db.query(ProviderNightQuota).filter_by(quarter_id=quarter_id, provider_id=user.id).first()
    target = override.target_nights if override else q.default_quota

    prefs = db.query(NightPreference).filter_by(quarter_id=quarter_id, provider_id=user.id).all()
    preferred = sum(1 for p in prefs if p.preference == "preferred")
    can_work = sum(1 for p in prefs if p.preference == "can_work")
    blocked = db.query(BlockedNight).filter_by(quarter_id=quarter_id, provider_id=user.id).count()

    assigned = 0
    periods = db.query(SchedulePeriod.id).filter_by(rotation_key=quarter_id).all()
    period_ids = [p[0] for p in periods]
    if period_ids:
        assigned = db.query(PeriodAssignment).filter(
            PeriodAssignment.period_id.in_(period_ids),
            PeriodAssignment.provider_id == user.id,
        ).count()

    return {
        "quarter_id": q.id,
        "status": q.status,
        "window_open": _window_open(q),
        "preference_deadline": q.preference_deadline.isoformat() if q.preference_deadline else None,
        "target_nights": target,
        "preferred_count": preferred,
        "can_work_count": can_work,
        "blocked_count": blocked,
        "assigned_count": assigned,
    }


# ── Preferences ──────────────────────────────────────────────────────────────

@router.post("/quarters/{quarter_id}/preferences")
def set_preference(
    quarter_id: str,
    body: PreferenceSet,
    request: Request,
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)

    if not _window_open(q):
        raise HTTPException(status_code=400, detail="Self-scheduling is not currently open for this quarter")

    if body.preference not in VALID_PREFERENCES:
        raise HTTPException(status_code=400, detail=f"preference must be one of {sorted(VALID_PREFERENCES)}")

    if body.night_date < q.start_date or body.night_date > q.end_date:
        raise HTTPException(status_code=400, detail="night_date is outside this quarter")

    blocked = db.query(BlockedNight).filter_by(
        quarter_id=quarter_id, provider_id=user.id, night_date=body.night_date
    ).first()
    if blocked:
        raise HTTPException(status_code=400, detail="This night is blocked by your existing schedule and cannot be selected")

    row = db.query(NightPreference).filter_by(
        quarter_id=quarter_id, provider_id=user.id, night_date=body.night_date
    ).first()
    if row:
        row.preference = body.preference
    else:
        row = NightPreference(
            quarter_id=quarter_id, provider_id=user.id,
            night_date=body.night_date, preference=body.preference,
        )
        db.add(row)
    db.commit()
    return {"night_date": body.night_date.isoformat(), "preference": body.preference}


@router.delete("/quarters/{quarter_id}/preferences/{night_date}", status_code=204)
def clear_preference(
    quarter_id: str,
    night_date: date,
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    if not _window_open(q):
        raise HTTPException(status_code=400, detail="Self-scheduling is not currently open for this quarter")

    row = db.query(NightPreference).filter_by(
        quarter_id=quarter_id, provider_id=user.id, night_date=night_date
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return None


# ── Final schedule (published) ──────────────────────────────────────────────

@router.get("/quarters/{quarter_id}/my-schedule")
def my_schedule(
    quarter_id: str,
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _get_quarter_or_404(db, quarter_id)
    periods = db.query(SchedulePeriod).filter_by(rotation_key=quarter_id).order_by(SchedulePeriod.period_date).all()
    period_ids = [p.id for p in periods]
    period_by_id = {p.id: p for p in periods}

    nights = []
    if period_ids:
        assigns = db.query(PeriodAssignment).filter(
            PeriodAssignment.period_id.in_(period_ids),
            PeriodAssignment.provider_id == user.id,
        ).all()
        for a in assigns:
            per = period_by_id.get(a.period_id)
            if per:
                nights.append({"date": per.period_date.isoformat(), "lane": per.shift_type})

    nights.sort(key=lambda n: n["date"])
    return {"quarter_id": q.id, "status": q.status, "nights": nights}
