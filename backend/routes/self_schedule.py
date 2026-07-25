"""
Self-scheduling API (end-user facing).

Implements the First-Come-First-Served (FCFS) method: a user whose division
uses method 'fcfs' with an open self-scheduling window can claim open shifts
(up to max staffing) and release their own claims. Viewing the schedule is
always allowed; claiming requires the window to be open.

Other methods (priority, wave) are declared per division but enforced by
separate engines — this router reports them as "not open for self-serve".

  GET  /api/self-schedule/context                 — user's division + policy + rotations
  GET  /api/self-schedule/periods?year=&month=    — the month's shifts for the user's division
  POST /api/self-schedule/claim    {period_id}    — claim an open slot (FCFS)
  POST /api/self-schedule/release  {period_id}    — release the user's own claim
"""

import logging
from calendar import monthrange
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from backend.models import (
    Division,
    Faculty,
    PeriodAssignment,
    SchedulePeriod,
    get_db,
)
from backend.auth import get_current_user
from backend.routes.config import _get
from backend.routes.divisions import _parse_scheduling_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/self-schedule", tags=["self-schedule"])


class PeriodRef(BaseModel):
    period_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _division_rotations(db: Session, division_key: str) -> list[dict]:
    """Shift-based rotations owned by a division."""
    return [
        r for r in (_get(db, "rotations") or [])
        if r.get("division_key") == division_key and r.get("model") == "shift_based"
    ]


def _shift_labels(rotations: list[dict]) -> dict[tuple, dict]:
    """(rotation_key, shift_key) -> shift definition, for labelling periods."""
    out = {}
    for r in rotations:
        for s in r.get("shifts", []):
            out[(r["key"], s["key"])] = s
    return out


def _require_division(user: Faculty, db: Session) -> Division:
    if not user.division_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You are not assigned to a division yet. Contact an admin.")
    division = db.query(Division).filter_by(key=user.division_key).first()
    if not division:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Your division no longer exists. Contact an admin.")
    return division


def _serialize_period(p: SchedulePeriod, user_id: str, shift_defs: dict,
                      can_claim_window: bool) -> dict:
    providers = [a for a in p.assignments if a.role == "provider"]
    provider_count = len(providers)
    mine = next((a for a in p.assignments if a.provider_id == user_id), None)

    if provider_count < p.min_slots:
        fill_state = "understaffed"
    elif provider_count < p.slots_needed:
        fill_state = "below_target"
    elif provider_count <= p.slots_needed:
        fill_state = "at_target"
    else:
        fill_state = "above_target"

    sdef = shift_defs.get((p.rotation_key, p.shift_type), {})
    return {
        "id": p.id,
        "rotation_key": p.rotation_key,
        "period_date": p.period_date.isoformat(),
        "shift_type": p.shift_type,
        "shift_label": sdef.get("label", p.shift_type.title()),
        "start_time": p.start_time,
        "end_time": p.end_time,
        "min_slots": p.min_slots,
        "target_slots": p.slots_needed,
        "max_slots": p.max_slots,
        "provider_count": provider_count,
        "fill_state": fill_state,
        "colleagues": [a.provider.name if a.provider else a.provider_id
                       for a in providers],
        "claimed_by_me": mine is not None,
        "my_claim_is_self": bool(mine and not mine.is_manual),
        # Claimable = window open, room left, and I'm not already on it
        "claimable": can_claim_window and provider_count < p.max_slots and mine is None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/context")
def context(user: Faculty = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.division_key:
        return {"has_division": False}
    division = db.query(Division).filter_by(key=user.division_key).first()
    if not division:
        return {"has_division": False}

    cfg = _parse_scheduling_config(division)
    rotations = _division_rotations(db, division.key)
    return {
        "has_division": True,
        "division": {"key": division.key, "label": division.label, "color": division.color},
        "method": cfg.get("method"),
        "cadence": cfg.get("cadence"),
        "open": bool(cfg.get("self_scheduling_open")),
        "notes": cfg.get("notes", ""),
        # Self-serve claiming is live only for FCFS with an open window (for now)
        "self_serve": cfg.get("method") == "fcfs",
        "can_claim": cfg.get("method") == "fcfs" and bool(cfg.get("self_scheduling_open")),
        "rotations": [{"key": r["key"], "label": r["label"]} for r in rotations],
    }


@router.get("/periods")
def periods(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    user: Faculty = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    division = _require_division(user, db)
    cfg = _parse_scheduling_config(division)
    rotations = _division_rotations(db, division.key)
    rotation_keys = [r["key"] for r in rotations]
    if not rotation_keys:
        return {"periods": [], "can_claim": False}

    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    can_claim_window = cfg.get("method") == "fcfs" and bool(cfg.get("self_scheduling_open"))

    rows = (
        db.query(SchedulePeriod)
        .options(joinedload(SchedulePeriod.assignments).joinedload(PeriodAssignment.provider))
        .filter(SchedulePeriod.rotation_key.in_(rotation_keys),
                SchedulePeriod.period_date >= start,
                SchedulePeriod.period_date <= end)
        .order_by(SchedulePeriod.period_date, SchedulePeriod.start_time)
        .all()
    )
    shift_defs = _shift_labels(rotations)
    return {
        "can_claim": can_claim_window,
        "periods": [_serialize_period(p, user.id, shift_defs, can_claim_window) for p in rows],
    }


@router.post("/claim")
def claim(body: PeriodRef, user: Faculty = Depends(get_current_user),
          db: Session = Depends(get_db)):
    division = _require_division(user, db)
    cfg = _parse_scheduling_config(division)

    if cfg.get("method") != "fcfs":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Your division doesn't use first-come-first-served self-scheduling.")
    if not cfg.get("self_scheduling_open"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Self-scheduling is closed for your division right now.")

    period = (
        db.query(SchedulePeriod)
        .options(joinedload(SchedulePeriod.assignments))
        .filter_by(id=body.period_id)
        .first()
    )
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found.")

    rotation_keys = {r["key"] for r in _division_rotations(db, division.key)}
    if period.rotation_key not in rotation_keys:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="That shift isn't in your division.")

    if any(a.provider_id == user.id for a in period.assignments):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="You're already on this shift.")

    provider_count = sum(1 for a in period.assignments if a.role == "provider")
    if provider_count >= period.max_slots:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This shift just filled up.")

    # Same-day double-booking is allowed but flagged
    same_day = (
        db.query(PeriodAssignment)
        .join(SchedulePeriod)
        .filter(PeriodAssignment.provider_id == user.id,
                SchedulePeriod.period_date == period.period_date,
                SchedulePeriod.id != period.id)
        .count()
    )

    db.add(PeriodAssignment(
        period_id=period.id,
        provider_id=user.id,
        role="provider",
        status="assigned",
        is_manual=False,        # self-claimed
        assigned_by=user.id,
    ))
    db.commit()
    logger.info("User %s claimed period %s (fcfs)", user.id, period.id)

    result = {"claimed": True, "period_id": period.id}
    if same_day:
        result["warning"] = f"Heads up — you already have another shift on {period.period_date.isoformat()}."
    return result


@router.post("/release")
def release(body: PeriodRef, user: Faculty = Depends(get_current_user),
            db: Session = Depends(get_db)):
    division = _require_division(user, db)
    cfg = _parse_scheduling_config(division)

    assignment = (
        db.query(PeriodAssignment)
        .filter_by(period_id=body.period_id, provider_id=user.id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="You're not on this shift.")
    if assignment.is_manual:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="An admin placed you on this shift — ask them to remove you.")
    if not cfg.get("self_scheduling_open"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Self-scheduling is closed, so shifts can't be dropped right now.")

    db.delete(assignment)
    db.commit()
    logger.info("User %s released period %s", user.id, body.period_id)
    return {"released": True, "period_id": body.period_id}
