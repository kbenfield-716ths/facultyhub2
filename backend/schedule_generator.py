"""
Schedule Generator — STUB

The original PCCM-specific schedule generator has been replaced.
This module will be rebuilt as a config-driven, shift-based scheduler
during Week 2–3 of the FacultyHubAdaptable development roadmap.

For now it exposes a no-op function so any existing imports don't crash.
"""

import logging
logger = logging.getLogger(__name__)


def generate_schedule(*args, **kwargs):
    """Placeholder — not yet implemented for the new config-driven model."""
    logger.warning("generate_schedule called but scheduler is not yet implemented.")
    return {
        "success": False,
        "error": "Schedule generator not yet available. It will be rebuilt in Week 2.",
        "assignments": [],
    }


def get_schedule_view(*args, **kwargs):
    """Placeholder — returns an empty view structure."""
    logger.warning("get_schedule_view called but scheduler is not yet implemented.")
    return {"faculty": [], "weeks": [], "grid": {}}


# Stub constant — service requirements will be config-driven in the new model
SERVICE_REQUIREMENTS: dict = {}
