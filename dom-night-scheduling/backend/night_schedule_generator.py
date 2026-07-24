"""
Night-shift schedule builder — DOM Hospitalist Nights.

Builds the Admitter / Nocturnist assignments for every night in a Quarter.

Priority order (per Kyle's spec):
  1. Fill every hole — this is the primary goal. Every SchedulePeriod
     (date + lane) should get a provider if ANY eligible provider exists,
     even one with no preference recorded for that night.
  2. Among eligible candidates for a hole, prefer providers who marked that
     night "preferred", then "can_work", then anyone eligible with no
     preference at all.
  3. Within a preference tier, prefer the provider furthest below their
     quarterly quota (fairness). Ties broken by provider id for determinism.

Hard constraints (never violated):
  - A provider with a BlockedNight for that date is never assigned that
    date, in either lane.
  - A provider is never assigned to both lanes the same night.
  - A provider qualified for only one lane (Faculty.extra_config["lanes"])
    is only assigned within that lane. No `lanes` entry = qualified for both.

This module is pure / preview-friendly: `compute_assignments` does not write
to the database. `apply_assignments` performs the actual write + commit and
is called separately once an admin approves the preview.
"""

import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .models import (
    Faculty, Quarter, SchedulePeriod, PeriodAssignment,
    BlockedNight, NightPreference, ProviderNightQuota,
)

logger = logging.getLogger(__name__)

# Lower rank = more preferred. None (no preference recorded) sorts last.
PREF_RANK = {"preferred": 0, "can_work": 1, None: 2}


def _provider_lanes(faculty: Faculty) -> Optional[List[str]]:
    """Lanes a provider is qualified for, or None meaning 'any lane'."""
    try:
        extra = json.loads(faculty.extra_config or "{}")
    except (json.JSONDecodeError, TypeError):
        extra = {}
    lanes = extra.get("lanes")
    if not lanes:
        return None
    return lanes


def compute_assignments(db: Session, quarter: Quarter) -> dict:
    """
    Build a preview assignment plan for `quarter` without writing to the DB.

    Returns:
      {
        "success": True,
        "total_slots": int,             # all periods in the quarter
        "auto_slots": int,               # periods not already manually assigned
        "filled": int,                   # auto_slots - len(unfilled)
        "unfilled": [{"date","lane"}],
        "assignments": [                 # newly proposed (non-manual) assignments
          {"date","lane","provider_id","provider_name","reason","period_id"}
        ],
        "manual_assignments": [...],     # pre-existing manual assignments (kept as-is)
        "quota_summary": [
          {"provider_id","name","target","assigned"}
        ],
      }
    """
    periods = (
        db.query(SchedulePeriod)
        .filter(
            SchedulePeriod.rotation_key == quarter.id,
            SchedulePeriod.period_date >= quarter.start_date,
            SchedulePeriod.period_date <= quarter.end_date,
        )
        .order_by(SchedulePeriod.period_date, SchedulePeriod.shift_type)
        .all()
    )

    # Exclude admin-only accounts (e.g. the system ADMIN user) that have not
    # been explicitly opted into night-shift lanes via extra_config["lanes"].
    # Admins who ARE also night-shift providers should have "lanes" set, which
    # keeps them eligible here.
    providers = [
        p for p in db.query(Faculty).filter_by(active=True).all()
        if not p.is_admin or _provider_lanes(p) is not None
    ]
    provider_lanes = {p.id: _provider_lanes(p) for p in providers}
    provider_names = {p.id: p.name for p in providers}

    # Hard-blocked nights: (provider_id, date)
    blocked = {
        (b.provider_id, b.night_date)
        for b in db.query(BlockedNight).filter_by(quarter_id=quarter.id).all()
    }

    # Preferences: (provider_id, date) -> "preferred" | "can_work"
    prefs: Dict[tuple, str] = {
        (p.provider_id, p.night_date): p.preference
        for p in db.query(NightPreference).filter_by(quarter_id=quarter.id).all()
    }

    period_by_id = {p.id: p for p in periods}
    period_ids = list(period_by_id.keys())

    existing_manual = []
    if period_ids:
        existing_manual = (
            db.query(PeriodAssignment)
            .filter(
                PeriodAssignment.period_id.in_(period_ids),
                PeriodAssignment.is_manual == True,  # noqa: E712
            )
            .all()
        )

    assigned_night = {}     # (provider_id, date) -> lane already worked
    counts: Dict[str, int] = defaultdict(int)   # provider_id -> nights assigned
    manual_assignments = []
    manual_period_ids = set()
    for a in existing_manual:
        per = period_by_id.get(a.period_id)
        if not per:
            continue
        manual_period_ids.add(a.period_id)
        assigned_night[(a.provider_id, per.period_date)] = per.shift_type
        counts[a.provider_id] += 1
        manual_assignments.append({
            "date": per.period_date.isoformat(),
            "lane": per.shift_type,
            "provider_id": a.provider_id,
            "provider_name": provider_names.get(a.provider_id, a.provider_id),
            "reason": "manual",
            "period_id": per.id,
        })

    # Quotas: per-provider override, else quarter default
    overrides = {
        q.provider_id: q.target_nights
        for q in db.query(ProviderNightQuota).filter_by(quarter_id=quarter.id).all()
    }
    targets = {p.id: overrides.get(p.id, quarter.default_quota) for p in providers}

    results = []
    unfilled = []

    auto_periods = [p for p in periods if p.id not in manual_period_ids]

    for period in auto_periods:
        d = period.period_date
        lane = period.shift_type

        candidates = []
        for p in providers:
            pid = p.id
            if (pid, d) in blocked:
                continue
            if (pid, d) in assigned_night:
                continue  # already working the other lane tonight
            lanes = provider_lanes[pid]
            if lanes is not None and lane not in lanes:
                continue
            pref = prefs.get((pid, d))
            remaining = targets.get(pid, 0) - counts[pid]
            candidates.append((pid, pref, remaining))

        if not candidates:
            unfilled.append({"date": d.isoformat(), "lane": lane})
            continue

        # Preference tier first (preferred > can_work > none),
        # then most nights still needed (fairness), then id for determinism.
        candidates.sort(key=lambda c: (PREF_RANK.get(c[1], 2), -c[2], c[0]))
        chosen_pid, chosen_pref, _ = candidates[0]

        results.append({
            "date": d.isoformat(),
            "lane": lane,
            "provider_id": chosen_pid,
            "provider_name": provider_names.get(chosen_pid, chosen_pid),
            "reason": chosen_pref if chosen_pref else "fill",
            "period_id": period.id,
        })
        assigned_night[(chosen_pid, d)] = lane
        counts[chosen_pid] += 1

    quota_summary = [
        {
            "provider_id": p.id,
            "name": p.name,
            "target": targets.get(p.id, 0),
            "assigned": counts.get(p.id, 0),
        }
        for p in providers
    ]
    quota_summary.sort(key=lambda r: r["name"])

    return {
        "success": True,
        "total_slots": len(periods),
        "auto_slots": len(auto_periods),
        "filled": len(auto_periods) - len(unfilled),
        "unfilled": unfilled,
        "assignments": results,
        "manual_assignments": manual_assignments,
        "quota_summary": quota_summary,
    }


def apply_assignments(db: Session, quarter: Quarter, plan: dict, admin_id: Optional[str] = None) -> dict:
    """
    Persist the proposed (non-manual) assignments from `plan` to the
    database. Replaces any prior auto-generated (is_manual=False)
    PeriodAssignment rows for this quarter's periods; manual rows are
    left untouched.
    """
    periods = db.query(SchedulePeriod).filter_by(rotation_key=quarter.id).all()
    period_ids = [p.id for p in periods]

    if period_ids:
        db.query(PeriodAssignment).filter(
            PeriodAssignment.period_id.in_(period_ids),
            PeriodAssignment.is_manual == False,  # noqa: E712
        ).delete(synchronize_session=False)

    for a in plan.get("assignments", []):
        db.add(PeriodAssignment(
            period_id=a["period_id"],
            provider_id=a["provider_id"],
            status="assigned",
            is_manual=False,
            assigned_by=admin_id,
            note=f"auto: {a['reason']}",
        ))

    if quarter.status == "open_for_preferences":
        quarter.status = "building"

    db.commit()
    return {"applied": len(plan.get("assignments", []))}
