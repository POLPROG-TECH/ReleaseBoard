"""Release calendar validation — schema-driven import and structural checks.

All validation uses the same JSON Schema source of truth as the rest of the app.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

_LEGACY_PHASES = frozenset({"dev", "sit", "uat", "preprod", "prod"})

# Enterprise default milestones — canonical order
_DEFAULT_MILESTONES = (
    "feature_freeze",
    "promote_sit",
    "sit_start",
    "sit_end",
    "fov_readiness",
    "promote_uat",
    "uat_end",
    "hard_code_freeze",
    "uat2_install",
    "uat2_end",
    "prod_install",
)

_VALID_PHASES = frozenset(_DEFAULT_MILESTONES) | _LEGACY_PHASES
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCHEMA_CACHE: dict[str, Any] | None = None

# Safety limits for import payloads
MAX_EVENTS = 500
MAX_MONTHS = 120
MAX_NAME_LENGTH = 200
MAX_NOTES_LENGTH = 2000
MAX_LABEL_LENGTH = 200
MAX_EVENT_NOTES_LENGTH = 500
MAX_IMPORT_SIZE_BYTES = 1_048_576  # 1 MB


def _load_calendar_schema() -> dict[str, Any]:
    """Load the release_calendar sub-schema from the main config schema."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE
    schema_path = Path(__file__).resolve().parent.parent / "config" / "schema.json"
    with open(schema_path, encoding="utf-8") as f:
        full_schema = json.load(f)
    _SCHEMA_CACHE = full_schema.get("properties", {}).get("release_calendar", {})
    return _SCHEMA_CACHE


def get_import_schema_example() -> dict[str, Any]:
    """Return an example JSON structure for calendar import."""
    return {
        "name": "Q2 2026 Release Plan",
        "year": 2026,
        "notes": "Sprint-based release schedule",
        "events": [
            {
                "date": "2026-04-01",
                "phase": "feature_freeze",
                "label": "Sprint 7 — Feature Freeze",
            },
            {
                "date": "2026-04-03",
                "phase": "promote_sit",
                "label": "Sprint 7 — Promote SIT",
            },
            {
                "date": "2026-04-04",
                "phase": "sit_start",
                "label": "Sprint 7 — SIT Start",
            },
            {
                "date": "2026-04-11",
                "phase": "sit_end",
                "label": "Sprint 7 — SIT End",
            },
            {
                "date": "2026-04-14",
                "phase": "fov_readiness",
                "label": "Sprint 7 — FOV / Release Notes",
            },
            {
                "date": "2026-04-15",
                "phase": "promote_uat",
                "label": "Sprint 7 — Promote UAT",
            },
            {
                "date": "2026-04-22",
                "phase": "uat_end",
                "label": "Sprint 7 — UAT End",
            },
            {
                "date": "2026-04-23",
                "phase": "hard_code_freeze",
                "label": "Sprint 7 — Hard Code Freeze",
            },
            {
                "date": "2026-04-25",
                "phase": "uat2_install",
                "label": "Sprint 7 — UAT2 Install",
            },
            {
                "date": "2026-04-28",
                "phase": "uat2_end",
                "label": "Sprint 7 — UAT2 End",
            },
            {
                "date": "2026-05-02",
                "phase": "prod_install",
                "label": "Sprint 7 — PROD Install",
            },
        ],
        "months": [],
        "display": {
            "show_notes": True,
            "show_weekdays": True,
            "show_quarter_headers": True,
        },
    }


def get_import_schema_definition() -> dict[str, Any]:
    """Return the JSON Schema definition for the release calendar (for UI display)."""
    return _load_calendar_schema()


def validate_calendar_import(data: Any) -> list[str]:
    """Validate a release calendar import payload.

    Returns a list of human-readable error messages. An empty list means valid.
    Validation is strict — partial/ambiguous data is rejected.
    """
    errors: list[str] = []

    # --- Top-level structure ---
    if not isinstance(data, dict):
        return ["Import data must be a JSON object (dict), got " + type(data).__name__]

    allowed_keys = {"name", "year", "notes", "months", "events", "display"}
    extra = set(data.keys()) - allowed_keys
    if extra:
        errors.append(f"Unknown top-level fields: {', '.join(sorted(extra))}")

    # --- name ---
    if "name" in data:
        if not isinstance(data["name"], str):
            errors.append("'name' must be a string")
        elif len(data["name"]) > MAX_NAME_LENGTH:
            errors.append(
                f"'name' exceeds maximum length of {MAX_NAME_LENGTH} characters"
            )

    # --- year ---
    if "year" in data:
        y = data["year"]
        if not isinstance(y, int):
            errors.append("'year' must be an integer")
        elif y < 2000 or y > 2100:
            errors.append(f"'year' must be between 2000 and 2100, got {y}")

    # --- notes ---
    if "notes" in data:
        if not isinstance(data["notes"], str):
            errors.append("'notes' must be a string")
        elif len(data["notes"]) > MAX_NOTES_LENGTH:
            errors.append(
                f"'notes' exceeds maximum length of {MAX_NOTES_LENGTH} characters"
            )

    # --- events ---
    events = data.get("events", [])
    if not isinstance(events, list):
        errors.append("'events' must be an array")
    else:
        if len(events) > MAX_EVENTS:
            errors.append(
                f"'events' contains {len(events)} entries, maximum is {MAX_EVENTS}"
            )
        else:
            _validate_events(events, errors)

    # --- months (legacy, still accepted) ---
    months = data.get("months", [])
    if not isinstance(months, list):
        errors.append("'months' must be an array")
    else:
        if len(months) > MAX_MONTHS:
            errors.append(
                f"'months' contains {len(months)} entries, maximum is {MAX_MONTHS}"
            )
        else:
            _validate_months(months, errors)

    # --- display ---
    display = data.get("display")
    if display is not None:
        if not isinstance(display, dict):
            errors.append("'display' must be an object")
        else:
            display_keys = {"show_notes", "show_weekdays", "show_quarter_headers"}
            extra_d = set(display.keys()) - display_keys
            if extra_d:
                errors.append(f"Unknown fields in 'display': {', '.join(sorted(extra_d))}")
            for dk in display_keys:
                if dk in display and not isinstance(display[dk], bool):
                    errors.append(f"'display.{dk}' must be a boolean")

    # --- At least one data source ---
    if not events and not months:
        errors.append("Calendar must contain at least one entry in 'events' or 'months'")

    return errors


def _validate_events(events: list[Any], errors: list[str]) -> None:
    """Validate each event entry."""
    seen: set[tuple[str, str]] = set()
    for i, evt in enumerate(events):
        prefix = f"events[{i}]"
        if not isinstance(evt, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Required fields
        if "date" not in evt:
            errors.append(f"{prefix}: missing required field 'date'")
        if "phase" not in evt:
            errors.append(f"{prefix}: missing required field 'phase'")

        # Allowed fields
        allowed = {"date", "phase", "label", "notes"}
        extra = set(evt.keys()) - allowed
        if extra:
            errors.append(f"{prefix}: unknown fields: {', '.join(sorted(extra))}")

        # Date validation
        date_val = evt.get("date", "")
        if isinstance(date_val, str) and date_val:
            if not _DATE_RE.match(date_val):
                errors.append(f"{prefix}: 'date' must be YYYY-MM-DD format, got '{date_val}'")
            else:
                if not _is_real_date(date_val):
                    errors.append(f"{prefix}: '{date_val}' is not a valid calendar date")
        elif "date" in evt:
            errors.append(f"{prefix}: 'date' must be a non-empty string in YYYY-MM-DD format")

        # Phase validation
        phase_val = evt.get("phase", "")
        if isinstance(phase_val, str):
            if phase_val and phase_val not in _VALID_PHASES:
                errors.append(
                    f"{prefix}: 'phase' must be one of {sorted(_VALID_PHASES)}, got '{phase_val}'"
                )
        elif "phase" in evt:
            errors.append(f"{prefix}: 'phase' must be a string")

        # Optional strings
        for fld, max_len in (("label", MAX_LABEL_LENGTH), ("notes", MAX_EVENT_NOTES_LENGTH)):
            if fld in evt:
                if not isinstance(evt[fld], str):
                    errors.append(f"{prefix}: '{fld}' must be a string")
                elif len(evt[fld]) > max_len:
                    errors.append(
                        f"{prefix}: '{fld}' exceeds maximum length of {max_len} characters"
                    )

        # Duplicate detection
        if isinstance(date_val, str) and isinstance(phase_val, str) and date_val and phase_val:
            key = (date_val, phase_val)
            if key in seen:
                errors.append(f"{prefix}: duplicate event (date={date_val}, phase={phase_val})")
            seen.add(key)


def _validate_months(months: list[Any], errors: list[str]) -> None:
    """Validate legacy monthly entries."""
    seen_months: set[int] = set()
    for i, m in enumerate(months):
        prefix = f"months[{i}]"
        if not isinstance(m, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        if "month" not in m:
            errors.append(f"{prefix}: missing required field 'month'")
        else:
            mv = m["month"]
            if not isinstance(mv, int) or mv < 1 or mv > 12:
                errors.append(f"{prefix}: 'month' must be an integer 1-12")
            else:
                if mv in seen_months:
                    errors.append(f"{prefix}: duplicate month {mv}")
                seen_months.add(mv)

        # Optional year
        if "year" in m:
            yv = m["year"]
            if not isinstance(yv, int) or yv < 2000 or yv > 2100:
                errors.append(f"{prefix}: 'year' must be an integer 2000-2100")

        # Phases
        phases = m.get("phases")
        if phases is not None:
            if not isinstance(phases, dict):
                errors.append(f"{prefix}: 'phases' must be an object")
            else:
                extra = set(phases.keys()) - _VALID_PHASES
                if extra:
                    errors.append(f"{prefix}.phases: unknown phases: {', '.join(sorted(extra))}")
                for p, v in phases.items():
                    if p in _VALID_PHASES and isinstance(v, str) and v:
                        if not _DATE_RE.match(v):
                            errors.append(
                                f"{prefix}.phases.{p}: must be YYYY-MM-DD format, got '{v}'"
                            )
                        elif not _is_real_date(v):
                            errors.append(
                                f"{prefix}.phases.{p}: '{v}' is not a valid calendar date",
                            )

        # Notes
        if "notes" in m and not isinstance(m["notes"], str):
            errors.append(f"{prefix}: 'notes' must be a string")

        # Extra fields
        allowed = {"month", "year", "phases", "notes"}
        extra = set(m.keys()) - allowed
        if extra:
            errors.append(f"{prefix}: unknown fields: {', '.join(sorted(extra))}")


def _is_real_date(date_str: str) -> bool:
    """Check if a YYYY-MM-DD string represents a real calendar date."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def calendar_has_data(cal: dict[str, Any] | None) -> bool:
    """Return True if the calendar contains any meaningful data (events or months)."""
    if not cal or not isinstance(cal, dict):
        return False
    events = cal.get("events", [])
    months = cal.get("months", [])
    return bool(events) or bool(months)


def get_upcoming_milestones(cal: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract the next relevant milestone date for each phase.

    Returns a list of dicts: [{phase, date, label, days_remaining}], sorted by date.
    Considers both events and months data, preferring the nearest future date per phase.
    """
    if not cal or not isinstance(cal, dict):
        return []

    today = date.today()
    phase_dates: dict[str, tuple[str, str]] = {}  # phase -> (date_str, label)

    # From events — pick nearest future date per phase, or most recent past
    for evt in cal.get("events", []):
        if not isinstance(evt, dict):
            continue
        d = evt.get("date", "")
        p = evt.get("phase", "")
        if not d or not p or p not in _VALID_PHASES:
            continue
        label = evt.get("label", "")
        _update_phase_date(phase_dates, p, d, label, today)

    # From months — pick earliest date per phase
    for m in cal.get("months", []):
        if not isinstance(m, dict):
            continue
        phases = m.get("phases", {})
        if not isinstance(phases, dict):
            continue
        for p, d in phases.items():
            if p not in _VALID_PHASES or not d:
                continue
            _update_phase_date(phase_dates, p, d, "", today)

    # Build result sorted by date — iterate enterprise milestones first, then legacy
    milestone_order = _DEFAULT_MILESTONES + tuple(
        p for p in ("dev", "sit", "uat", "preprod", "prod")
    )
    result = []
    for phase in milestone_order:
        if phase not in phase_dates:
            continue
        d_str, label = phase_dates[phase]
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        delta = (d - today).days
        result.append({
            "phase": phase,
            "date": d_str,
            "label": label,
            "days_remaining": delta,
        })

    return result


def _update_phase_date(
    phase_dates: dict[str, tuple[str, str]],
    phase: str,
    date_str: str,
    label: str,
    today: date,
) -> None:
    """Select the best representative date for a phase.

    Prefers the nearest future date. If all are past, picks the most recent past date.
    """
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return

    if phase not in phase_dates:
        phase_dates[phase] = (date_str, label)
        return

    existing_str, _ = phase_dates[phase]
    try:
        existing = date.fromisoformat(existing_str)
    except ValueError:
        phase_dates[phase] = (date_str, label)
        return

    # Prefer nearest future date
    d_future = d >= today
    e_future = existing >= today

    if d_future and e_future:
        if d < existing:
            phase_dates[phase] = (date_str, label)
    elif (d_future and not e_future) or (not d_future and not e_future and d > existing):
        phase_dates[phase] = (date_str, label)
