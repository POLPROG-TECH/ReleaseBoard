"""Tests for releaseboard.calendar.validator — comprehensive coverage.

Covers: validate_calendar_import, calendar_has_data, get_upcoming_milestones,
get_import_schema_example, get_import_schema_definition, and edge cases.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

from releaseboard.calendar.validator import (
    _DEFAULT_MILESTONES,
    _VALID_PHASES,
    MAX_EVENTS,
    MAX_IMPORT_SIZE_BYTES,
    MAX_LABEL_LENGTH,
    MAX_MONTHS,
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    calendar_has_data,
    get_import_schema_definition,
    get_import_schema_example,
    get_upcoming_milestones,
    validate_calendar_import,
)

# ---------------------------------------------------------------------------
# Fixtures: valid payloads
# ---------------------------------------------------------------------------

def _valid_event_payload() -> dict[str, Any]:
    """Minimal valid calendar with a single event."""
    return {
        "name": "Test Calendar",
        "year": 2026,
        "events": [
            {"date": "2026-04-01", "phase": "feature_freeze", "label": "Sprint 7"},
        ],
    }


def _valid_month_payload() -> dict[str, Any]:
    """Minimal valid calendar with a single month entry."""
    return {
        "name": "Monthly Calendar",
        "year": 2026,
        "months": [
            {
                "month": 4,
                "phases": {
                    "feature_freeze": "2026-04-01",
                    "sit_start": "2026-04-04",
                    "prod_install": "2026-04-28",
                },
            }
        ],
    }


def _full_event_payload() -> dict[str, Any]:
    """Calendar with all 11 enterprise milestones as events."""
    base_date = date(2026, 4, 1)
    events = []
    for i, phase in enumerate(_DEFAULT_MILESTONES):
        d = base_date + timedelta(days=i * 3)
        events.append({
            "date": d.isoformat(),
            "phase": phase,
            "label": f"Sprint 7 — {phase}",
        })
    return {
        "name": "Q2 2026 Full Release Plan",
        "year": 2026,
        "notes": "Complete milestone schedule",
        "events": events,
        "display": {
            "show_notes": True,
            "show_weekdays": True,
            "show_quarter_headers": True,
        },
    }


# ===========================================================================
# validate_calendar_import — happy path
# ===========================================================================


class TestValidateCalendarImportValid:
    """Valid import payloads must produce zero errors."""

    def test_valid_events_only(self):
        errors = validate_calendar_import(_valid_event_payload())
        assert errors == []

    def test_valid_months_only(self):
        errors = validate_calendar_import(_valid_month_payload())
        assert errors == []

    def test_valid_full_events(self):
        errors = validate_calendar_import(_full_event_payload())
        assert errors == []

    def test_valid_events_and_months_combined(self):
        data = _valid_event_payload()
        data["months"] = [
            {"month": 5, "phases": {"sit_start": "2026-05-01"}},
        ]
        errors = validate_calendar_import(data)
        assert errors == []

    def test_valid_legacy_phases(self):
        data = {
            "events": [{"date": "2026-06-01", "phase": "dev"}],
        }
        errors = validate_calendar_import(data)
        assert errors == []

    def test_valid_minimal_event(self):
        """An event with only required fields (date + phase) is valid."""
        data = {"events": [{"date": "2026-01-15", "phase": "sit_start"}]}
        errors = validate_calendar_import(data)
        assert errors == []

    def test_valid_display_options(self):
        data = _valid_event_payload()
        data["display"] = {
            "show_notes": False,
            "show_weekdays": True,
            "show_quarter_headers": False,
        }
        errors = validate_calendar_import(data)
        assert errors == []

    def test_optional_fields_absent(self):
        """Missing name, year, notes, display is fine as long as events exist."""
        data = {"events": [{"date": "2026-03-01", "phase": "prod_install"}]}
        errors = validate_calendar_import(data)
        assert errors == []

    def test_event_with_notes_field(self):
        data = {
            "events": [
                {"date": "2026-04-01", "phase": "sit_start", "notes": "Delayed 1 day"},
            ],
        }
        errors = validate_calendar_import(data)
        assert errors == []


# ===========================================================================
# validate_calendar_import — top-level errors
# ===========================================================================


class TestValidateCalendarImportTopLevel:
    """Top-level structure validation."""

    def test_not_a_dict(self):
        errors = validate_calendar_import("not a dict")
        assert len(errors) == 1
        assert "JSON object" in errors[0]

    def test_list_instead_of_dict(self):
        errors = validate_calendar_import([{"date": "2026-01-01"}])
        assert len(errors) == 1
        assert "list" in errors[0]

    def test_none_input(self):
        errors = validate_calendar_import(None)
        assert len(errors) == 1
        assert "NoneType" in errors[0]

    def test_unknown_top_level_fields(self):
        data = _valid_event_payload()
        data["unknown_field"] = "bad"
        data["another"] = 123
        errors = validate_calendar_import(data)
        assert any("Unknown top-level fields" in e for e in errors)
        assert "another" in errors[0]
        assert "unknown_field" in errors[0]

    def test_empty_dict_no_data(self):
        errors = validate_calendar_import({})
        assert any("at least one entry" in e for e in errors)

    def test_empty_events_and_months(self):
        errors = validate_calendar_import({"events": [], "months": []})
        assert any("at least one entry" in e for e in errors)


# ===========================================================================
# validate_calendar_import — name / year / notes
# ===========================================================================


class TestValidateCalendarImportFields:
    """Field-level validation for name, year, notes."""

    def test_name_not_string(self):
        data = _valid_event_payload()
        data["name"] = 123
        errors = validate_calendar_import(data)
        assert any("'name' must be a string" in e for e in errors)

    def test_name_too_long(self):
        data = _valid_event_payload()
        data["name"] = "x" * (MAX_NAME_LENGTH + 1)
        errors = validate_calendar_import(data)
        assert any("exceeds maximum length" in e for e in errors)

    def test_name_at_max_length(self):
        data = _valid_event_payload()
        data["name"] = "x" * MAX_NAME_LENGTH
        errors = validate_calendar_import(data)
        assert errors == []

    def test_year_not_integer(self):
        data = _valid_event_payload()
        data["year"] = "2026"
        errors = validate_calendar_import(data)
        assert any("'year' must be an integer" in e for e in errors)

    def test_year_too_low(self):
        data = _valid_event_payload()
        data["year"] = 1999
        errors = validate_calendar_import(data)
        assert any("between 2000 and 2100" in e for e in errors)

    def test_year_too_high(self):
        data = _valid_event_payload()
        data["year"] = 2101
        errors = validate_calendar_import(data)
        assert any("between 2000 and 2100" in e for e in errors)

    def test_year_boundary_low(self):
        data = _valid_event_payload()
        data["year"] = 2000
        errors = validate_calendar_import(data)
        assert errors == []

    def test_year_boundary_high(self):
        data = _valid_event_payload()
        data["year"] = 2100
        errors = validate_calendar_import(data)
        assert errors == []

    def test_notes_not_string(self):
        data = _valid_event_payload()
        data["notes"] = 42
        errors = validate_calendar_import(data)
        assert any("'notes' must be a string" in e for e in errors)

    def test_notes_too_long(self):
        data = _valid_event_payload()
        data["notes"] = "n" * (MAX_NOTES_LENGTH + 1)
        errors = validate_calendar_import(data)
        assert any("exceeds maximum length" in e for e in errors)


# ===========================================================================
# validate_calendar_import — events validation
# ===========================================================================


class TestValidateCalendarImportEvents:
    """Event-level validation."""

    def test_events_not_array(self):
        data = {"events": "not an array"}
        errors = validate_calendar_import(data)
        assert any("'events' must be an array" in e for e in errors)

    def test_event_not_object(self):
        data = {"events": ["string instead of object"]}
        errors = validate_calendar_import(data)
        assert any("must be an object" in e for e in errors)

    def test_event_missing_date(self):
        data = {"events": [{"phase": "sit_start"}]}
        errors = validate_calendar_import(data)
        assert any("missing required field 'date'" in e for e in errors)

    def test_event_missing_phase(self):
        data = {"events": [{"date": "2026-04-01"}]}
        errors = validate_calendar_import(data)
        assert any("missing required field 'phase'" in e for e in errors)

    def test_event_bad_date_format(self):
        data = {"events": [{"date": "04/01/2026", "phase": "sit_start"}]}
        errors = validate_calendar_import(data)
        assert any("YYYY-MM-DD format" in e for e in errors)

    def test_event_invalid_calendar_date(self):
        data = {"events": [{"date": "2026-02-30", "phase": "sit_start"}]}
        errors = validate_calendar_import(data)
        assert any("not a valid calendar date" in e for e in errors)

    def test_event_date_empty_string(self):
        data = {"events": [{"date": "", "phase": "sit_start"}]}
        errors = validate_calendar_import(data)
        assert any("non-empty string" in e for e in errors)

    def test_event_date_not_string(self):
        data = {"events": [{"date": 20260401, "phase": "sit_start"}]}
        errors = validate_calendar_import(data)
        assert any("non-empty string" in e for e in errors)

    def test_event_invalid_phase(self):
        data = {"events": [{"date": "2026-04-01", "phase": "nonexistent_phase"}]}
        errors = validate_calendar_import(data)
        assert any("must be one of" in e for e in errors)

    def test_event_phase_not_string(self):
        data = {"events": [{"date": "2026-04-01", "phase": 123}]}
        errors = validate_calendar_import(data)
        assert any("'phase' must be a string" in e for e in errors)

    def test_event_unknown_fields(self):
        data = {"events": [{"date": "2026-04-01", "phase": "sit_start", "extra": "bad"}]}
        errors = validate_calendar_import(data)
        assert any("unknown fields" in e for e in errors)

    def test_event_label_not_string(self):
        data = {"events": [{"date": "2026-04-01", "phase": "sit_start", "label": 123}]}
        errors = validate_calendar_import(data)
        assert any("'label' must be a string" in e for e in errors)

    def test_event_label_too_long(self):
        data = {
            "events": [
                {
                    "date": "2026-04-01",
                    "phase": "sit_start",
                    "label": "L" * (MAX_LABEL_LENGTH + 1),
                }
            ],
        }
        errors = validate_calendar_import(data)
        assert any("exceeds maximum length" in e for e in errors)

    def test_event_duplicate_detection(self):
        evt = {"date": "2026-04-01", "phase": "sit_start"}
        data = {"events": [evt, copy.deepcopy(evt)]}
        errors = validate_calendar_import(data)
        assert any("duplicate event" in e for e in errors)

    def test_max_events_exceeded(self):
        events = [
            {"date": f"2026-01-{str(i % 28 + 1).zfill(2)}", "phase": "sit_start", "label": f"E{i}"}
            for i in range(MAX_EVENTS + 1)
        ]
        # Make each unique by varying label (date+phase duplicates are separate)
        for i, e in enumerate(events):
            e["date"] = f"2099-{str(i // 28 + 1).zfill(2)}-{str(i % 28 + 1).zfill(2)}"
        data = {"events": events}
        errors = validate_calendar_import(data)
        assert any(f"maximum is {MAX_EVENTS}" in e for e in errors)

    def test_all_enterprise_phases_accepted(self):
        """Every enterprise milestone is accepted as a valid phase."""
        for phase in _DEFAULT_MILESTONES:
            data = {"events": [{"date": "2026-06-15", "phase": phase}]}
            errors = validate_calendar_import(data)
            assert errors == [], f"Phase '{phase}' unexpectedly rejected: {errors}"

    def test_all_legacy_phases_accepted(self):
        """Every legacy phase is accepted."""
        for phase in ("dev", "sit", "uat", "preprod", "prod"):
            data = {"events": [{"date": "2026-06-15", "phase": phase}]}
            errors = validate_calendar_import(data)
            assert errors == [], f"Phase '{phase}' unexpectedly rejected: {errors}"


# ===========================================================================
# validate_calendar_import — months validation
# ===========================================================================


class TestValidateCalendarImportMonths:
    """Monthly entry validation."""

    def test_months_not_array(self):
        data = {"months": "not an array"}
        errors = validate_calendar_import(data)
        assert any("'months' must be an array" in e for e in errors)

    def test_month_not_object(self):
        data = {"months": [42]}
        errors = validate_calendar_import(data)
        assert any("must be an object" in e for e in errors)

    def test_month_missing_month_field(self):
        data = {"months": [{"phases": {"sit_start": "2026-04-04"}}]}
        errors = validate_calendar_import(data)
        assert any("missing required field 'month'" in e for e in errors)

    def test_month_out_of_range(self):
        data = {"months": [{"month": 13}]}
        errors = validate_calendar_import(data)
        assert any("1-12" in e for e in errors)

    def test_month_zero(self):
        data = {"months": [{"month": 0}]}
        errors = validate_calendar_import(data)
        assert any("1-12" in e for e in errors)

    def test_month_not_integer(self):
        data = {"months": [{"month": "April"}]}
        errors = validate_calendar_import(data)
        assert any("must be an integer 1-12" in e for e in errors)

    def test_duplicate_months(self):
        data = {
            "months": [
                {"month": 4, "phases": {"sit_start": "2026-04-04"}},
                {"month": 4, "phases": {"sit_end": "2026-04-11"}},
            ],
        }
        errors = validate_calendar_import(data)
        assert any("duplicate month 4" in e for e in errors)

    def test_month_phases_not_object(self):
        data = {"months": [{"month": 4, "phases": "invalid"}]}
        errors = validate_calendar_import(data)
        assert any("'phases' must be an object" in e for e in errors)

    def test_month_phase_bad_date(self):
        data = {"months": [{"month": 4, "phases": {"sit_start": "bad-date"}}]}
        errors = validate_calendar_import(data)
        assert any("YYYY-MM-DD" in e for e in errors)

    def test_month_phase_invalid_calendar_date(self):
        data = {"months": [{"month": 4, "phases": {"sit_start": "2026-04-31"}}]}
        errors = validate_calendar_import(data)
        assert any("not a valid calendar date" in e for e in errors)

    def test_month_unknown_phase(self):
        data = {"months": [{"month": 4, "phases": {"unknown_phase": "2026-04-01"}}]}
        errors = validate_calendar_import(data)
        assert any("unknown phases" in e for e in errors)

    def test_month_unknown_fields(self):
        data = {"months": [{"month": 4, "extra": "bad"}]}
        errors = validate_calendar_import(data)
        assert any("unknown fields" in e for e in errors)

    def test_month_notes_not_string(self):
        data = {"months": [{"month": 4, "notes": 123}]}
        errors = validate_calendar_import(data)
        assert any("'notes' must be a string" in e for e in errors)

    def test_max_months_exceeded(self):
        months = [{"month": (i % 12) + 1} for i in range(MAX_MONTHS + 1)]
        data = {"months": months}
        errors = validate_calendar_import(data)
        assert any(f"maximum is {MAX_MONTHS}" in e for e in errors)


# ===========================================================================
# validate_calendar_import — display validation
# ===========================================================================


class TestValidateCalendarImportDisplay:
    """Display options validation."""

    def test_display_not_object(self):
        data = _valid_event_payload()
        data["display"] = "bad"
        errors = validate_calendar_import(data)
        assert any("'display' must be an object" in e for e in errors)

    def test_display_unknown_fields(self):
        data = _valid_event_payload()
        data["display"] = {"show_notes": True, "unknown_flag": True}
        errors = validate_calendar_import(data)
        assert any("Unknown fields in 'display'" in e for e in errors)

    def test_display_value_not_boolean(self):
        data = _valid_event_payload()
        data["display"] = {"show_notes": "yes"}
        errors = validate_calendar_import(data)
        assert any("must be a boolean" in e for e in errors)


# ===========================================================================
# calendar_has_data
# ===========================================================================


class TestCalendarHasData:
    def test_none(self):
        assert calendar_has_data(None) is False

    def test_empty_dict(self):
        assert calendar_has_data({}) is False

    def test_not_dict(self):
        assert calendar_has_data("string") is False

    def test_empty_events_and_months(self):
        assert calendar_has_data({"events": [], "months": []}) is False

    def test_has_events(self):
        assert calendar_has_data({"events": [{"date": "2026-01-01", "phase": "dev"}]}) is True

    def test_has_months(self):
        assert calendar_has_data({"months": [{"month": 1}]}) is True


# ===========================================================================
# get_upcoming_milestones
# ===========================================================================


class TestGetUpcomingMilestones:
    def test_none_calendar(self):
        assert get_upcoming_milestones(None) == []

    def test_empty_calendar(self):
        assert get_upcoming_milestones({}) == []

    def test_events_produce_milestones(self):
        today = date.today()
        future = today + timedelta(days=10)
        cal = {
            "events": [
                {"date": future.isoformat(), "phase": "sit_start", "label": "SIT"},
            ],
        }
        milestones = get_upcoming_milestones(cal)
        assert len(milestones) == 1
        assert milestones[0]["phase"] == "sit_start"
        assert milestones[0]["date"] == future.isoformat()
        assert milestones[0]["days_remaining"] == 10

    def test_months_produce_milestones(self):
        today = date.today()
        future = today + timedelta(days=5)
        cal = {
            "months": [
                {"month": future.month, "phases": {"prod_install": future.isoformat()}},
            ],
        }
        milestones = get_upcoming_milestones(cal)
        assert len(milestones) == 1
        assert milestones[0]["phase"] == "prod_install"
        assert milestones[0]["days_remaining"] == 5

    def test_past_dates_have_negative_days(self):
        past = date.today() - timedelta(days=3)
        cal = {"events": [{"date": past.isoformat(), "phase": "uat_end"}]}
        milestones = get_upcoming_milestones(cal)
        assert len(milestones) == 1
        assert milestones[0]["days_remaining"] == -3

    def test_today_has_zero_days(self):
        today = date.today()
        cal = {"events": [{"date": today.isoformat(), "phase": "feature_freeze"}]}
        milestones = get_upcoming_milestones(cal)
        assert len(milestones) == 1
        assert milestones[0]["days_remaining"] == 0

    def test_enterprise_milestone_order_preserved(self):
        """Milestones should follow the enterprise canonical order."""
        today = date.today()
        events = []
        for i, phase in enumerate(_DEFAULT_MILESTONES):
            events.append({
                "date": (today + timedelta(days=i + 1)).isoformat(),
                "phase": phase,
            })
        cal = {"events": events}
        milestones = get_upcoming_milestones(cal)
        phases = [m["phase"] for m in milestones]
        assert phases == list(_DEFAULT_MILESTONES)

    def test_prefers_nearest_future_date(self):
        """When multiple events exist for the same phase, nearest future wins."""
        today = date.today()
        near = today + timedelta(days=2)
        far = today + timedelta(days=20)
        cal = {
            "events": [
                {"date": far.isoformat(), "phase": "sit_start"},
                {"date": near.isoformat(), "phase": "sit_start"},
            ],
        }
        milestones = get_upcoming_milestones(cal)
        assert len(milestones) == 1
        assert milestones[0]["date"] == near.isoformat()

    def test_invalid_date_skipped(self):
        cal = {"events": [{"date": "not-a-date", "phase": "sit_start"}]}
        milestones = get_upcoming_milestones(cal)
        assert milestones == []

    def test_invalid_phase_skipped(self):
        today = date.today()
        cal = {
            "events": [
                {"date": (today + timedelta(days=1)).isoformat(), "phase": "invalid_phase"},
            ],
        }
        milestones = get_upcoming_milestones(cal)
        assert milestones == []

    def test_combined_events_and_months(self):
        today = date.today()
        future1 = today + timedelta(days=5)
        future2 = today + timedelta(days=10)
        cal = {
            "events": [
                {"date": future1.isoformat(), "phase": "sit_start"},
            ],
            "months": [
                {"month": future2.month, "phases": {"prod_install": future2.isoformat()}},
            ],
        }
        milestones = get_upcoming_milestones(cal)
        phases = [m["phase"] for m in milestones]
        assert "sit_start" in phases
        assert "prod_install" in phases

    def test_label_carried_through(self):
        today = date.today()
        cal = {
            "events": [
                {
                    "date": (today + timedelta(days=1)).isoformat(),
                    "phase": "sit_start",
                    "label": "Sprint 7",
                },
            ],
        }
        milestones = get_upcoming_milestones(cal)
        assert milestones[0]["label"] == "Sprint 7"

    def test_non_dict_events_ignored(self):
        cal = {"events": ["not a dict", None, 42]}
        milestones = get_upcoming_milestones(cal)
        assert milestones == []

    def test_non_dict_months_ignored(self):
        cal = {"months": ["not a dict", None]}
        milestones = get_upcoming_milestones(cal)
        assert milestones == []


# ===========================================================================
# get_import_schema_example / get_import_schema_definition
# ===========================================================================


class TestSchemaHelpers:
    def test_example_is_valid(self):
        """The schema example itself must pass validation."""
        example = get_import_schema_example()
        errors = validate_calendar_import(example)
        assert errors == [], f"Schema example is invalid: {errors}"

    def test_example_has_all_enterprise_milestones(self):
        example = get_import_schema_example()
        phases_in_example = {e["phase"] for e in example.get("events", [])}
        for milestone in _DEFAULT_MILESTONES:
            assert milestone in phases_in_example, f"Example missing milestone: {milestone}"

    def test_schema_definition_is_dict(self):
        schema = get_import_schema_definition()
        assert isinstance(schema, dict)

    def test_schema_definition_has_properties(self):
        schema = get_import_schema_definition()
        assert "properties" in schema or "type" in schema


# ===========================================================================
# Constants consistency
# ===========================================================================


class TestConstants:
    def test_default_milestones_count(self):
        assert len(_DEFAULT_MILESTONES) == 11

    def test_default_milestones_order(self):
        expected = (
            "feature_freeze", "promote_sit", "sit_start", "sit_end",
            "fov_readiness", "promote_uat", "uat_end",
            "hard_code_freeze", "uat2_install", "uat2_end", "prod_install",
        )
        assert expected == _DEFAULT_MILESTONES

    def test_valid_phases_includes_all_milestones_and_legacy(self):
        for m in _DEFAULT_MILESTONES:
            assert m in _VALID_PHASES
        for lp in ("dev", "sit", "uat", "preprod", "prod"):
            assert lp in _VALID_PHASES

    def test_safety_limits_reasonable(self):
        assert MAX_EVENTS >= 100
        assert MAX_MONTHS >= 12
        assert MAX_NAME_LENGTH >= 100
        assert MAX_IMPORT_SIZE_BYTES >= 100_000


# ===========================================================================
# Multiple errors collected
# ===========================================================================


class TestMultipleErrors:
    def test_multiple_event_errors_collected(self):
        """Validator should collect all errors, not stop at first."""
        data = {
            "events": [
                {"date": "bad", "phase": "invalid"},
                {"phase": "sit_start"},  # missing date
                {"date": "2026-04-01"},  # missing phase
            ],
        }
        errors = validate_calendar_import(data)
        assert len(errors) >= 3

    def test_mixed_event_and_month_errors(self):
        data = {
            "events": [{"date": "bad", "phase": "sit_start"}],
            "months": [{"month": 13}],
        }
        errors = validate_calendar_import(data)
        assert len(errors) >= 2
