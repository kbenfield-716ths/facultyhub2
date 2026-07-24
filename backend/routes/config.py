"""
Instance configuration API.

GET  /api/config          — full config (admin only)
PUT  /api/config/{key}    — upsert one key (admin only)
GET  /api/config/public   — branding + features (unauthenticated, for UI bootstrap)
POST /api/config/setup    — complete the setup wizard (admin only)
"""

import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Optional

from backend.models import InstanceConfig, get_db
from backend.auth import require_admin, get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/config", tags=["config"])


# ── Default config written on first boot ─────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "group_name":        "",
    "org_name":          "",
    "app_name":          "Faculty Hub",
    "setup_complete":    False,
    "scheduling_model":  "shift_based",   # "shift_based" | "weekly_blocks"
    "shift_config": {
        "shifts": [
            {"key": "day",   "label": "Day Shift",   "start": "07:00", "end": "19:00", "slots_needed": 2},
            {"key": "night", "label": "Night Shift",  "start": "19:00", "end": "07:00", "slots_needed": 2},
        ]
    },
    "service_types":       [],   # populated by setup wizard
    "faculty_attributes":  [],   # populated by setup wizard
    "scheduling_rules": {
        "weeks_per_year":              52,
        "academic_year_start_month":   7,
        "min_staff_per_period":        2,
        "point_cost_time_off":         5,
        "point_reward_volunteer":      0,
    },
    "features": {
        "moonlighting":          False,
        "draft_system":          False,
        "service_availability":  True,
        "knowledge_base":        True,
        "messages":              True,
    },
    "branding": {
        "org_label":     "",
        "accent_color":  None,
    },
}

# Keys exposed to unauthenticated callers (for page bootstrap)
PUBLIC_KEYS = {"group_name", "org_name", "app_name", "branding", "features", "setup_complete"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(db: Session, key: str) -> Any:
    row = db.query(InstanceConfig).filter_by(key=key).first()
    if row is None:
        return DEFAULTS.get(key)
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return None


def _set(db: Session, key: str, value: Any) -> None:
    row = db.query(InstanceConfig).filter_by(key=key).first()
    encoded = json.dumps(value)
    if row:
        row.value = encoded
    else:
        db.add(InstanceConfig(key=key, value=encoded))
    db.commit()


def _all(db: Session) -> dict:
    """Return all keys, merging DB values over defaults."""
    config = dict(DEFAULTS)
    for row in db.query(InstanceConfig).all():
        try:
            config[row.key] = json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            pass
    return config


def seed_defaults(db: Session) -> None:
    """
    Called at startup.  Writes any default keys that are not yet in the DB,
    so the app always has a complete config even on a brand-new database.
    """
    existing_keys = {r.key for r in db.query(InstanceConfig.key).all()}
    for key, value in DEFAULTS.items():
        if key not in existing_keys:
            db.add(InstanceConfig(key=key, value=json.dumps(value)))
    db.commit()


# ── Pydantic ──────────────────────────────────────────────────────────────────

class ConfigSetRequest(BaseModel):
    value: Any


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/public")
def get_public_config(db: Session = Depends(get_db)):
    """
    Returns branding + feature flags.
    Called by index.html before login to populate the wordmark and decide
    which cards to show.  No authentication required.
    """
    full = _all(db)
    return {k: full[k] for k in PUBLIC_KEYS if k in full}


@router.get("")
def get_full_config(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Return the complete instance config (admin only)."""
    return _all(db)


@router.put("/{key}")
def set_config_key(
    key: str,
    body: ConfigSetRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Upsert a single config key (admin only)."""
    if key not in DEFAULTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown config key: '{key}'. Valid keys: {sorted(DEFAULTS.keys())}",
        )
    _set(db, key, body.value)
    logger.info("Config key '%s' updated by admin %s", key, admin.id)
    return {"key": key, "value": body.value}


@router.post("/setup")
def complete_setup(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """
    Mark setup as complete.  Called by the wizard's final step.
    Validates that the minimum required config is present before locking.
    """
    group_name = _get(db, "group_name")
    service_types = _get(db, "service_types")
    scheduling_model = _get(db, "scheduling_model")

    if not group_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_name must be set before completing setup.",
        )
    if scheduling_model == "shift_based":
        shift_config = _get(db, "shift_config")
        if not shift_config or not shift_config.get("shifts"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one shift must be defined in shift_config.",
            )
    else:
        if not service_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one service type must be defined.",
            )

    _set(db, "setup_complete", True)
    logger.info("Setup completed by admin %s", admin.id)
    return {"setup_complete": True, "group_name": group_name}
