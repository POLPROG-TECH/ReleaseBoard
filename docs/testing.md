# Testing Guide

ReleaseBoard has a comprehensive test suite with **1141 tests** covering all layers of the architecture. This guide explains how to run tests, understand the test organization, and add new tests.

## Table of Contents

- [Running Tests](#running-tests)
- [Test Organization](#test-organization)
  - [Core Tests](#core-tests)
  - [Feature Tests](#feature-tests)
  - [Integration Tests](#integration-tests)
- [Test Style](#test-style)
- [Fixtures](#fixtures)
- [Adding Tests](#adding-tests)

## Running Tests

```bash
# All tests
pytest

# Verbose
pytest -v

# With coverage
pytest --cov=releaseboard --cov-report=term-missing

# Specific file
pytest tests/test_readiness_analysis.py

# Specific test
pytest tests/test_config.py::TestBranchPatternOverrides::test_layer_override_takes_precedence
```

> **Note:** The full test suite contains 1223 tests. Run `pytest -q` for a compact summary or `pytest -v` for detailed per-test output.

## Test Organization

### Core Tests

| File | Coverage |
|:-----|:---------|
| `test_branch_pattern.py` | Pattern resolution, regex matching, template validation |
| `test_config.py` | Schema validation, loading, env vars, three-tier overrides, per-layer root URL resolution |
| `test_readiness_analysis.py` | All readiness status paths (ready, missing, stale, invalid, error) |
| `test_staleness.py` | Staleness detection, freshness labels |
| `test_metrics.py` | Metrics aggregation, layer breakdown, attention sorting |
| `test_renderer.py` | HTML rendering, file output, theme attributes, chart data |
| `test_theme.py` | Theme resolution, color mappings |
| `test_integration.py` | End-to-end: config to analysis to rendering |
| `test_service.py` | AnalysisService pipeline, progress callbacks, cancellation |
| `test_state.py` | AppState management, three-tier config state, SSE subscribers |

### Feature Tests

| File | Coverage |
|:-----|:---------|
| `test_git_providers.py` | GitProvider abstraction, SmartGitProvider selection, default-branch fallback |
| `test_error_classification.py` | GitErrorKind enum, `classify_git_error()`, HTTP status mapping, placeholder detection |
| `test_config_ui.py` | Config drawer UI, form/JSON/effective tabs, validation scoping |
| `test_config_persistence.py` | Config loading, atomic save, backup creation, validation on save |
| `test_config_resilience.py` | Config resilience under edge cases, corrupt files, missing keys |
| `test_config_schema_layout.py` | Schema validation edge cases, effective value validation, layout rules |
| `test_config_save_compliance.py` | Config save compliance, backup rotation, file locking |
| `test_dashboard_ui.py` | Dashboard layout, toolbar, status bar, drag-and-drop, detail modal |
| `test_ui_dashboard_sections.py` | UI/UX interactions, inherited value display, branch pattern indicators |
| `test_github_public_repos.py` | Public GitHub repos, unauthenticated API access, enriched metadata |
| `test_provider_parsing_errors.py` | Provider-specific features, URL derivation, error parsing |
| `test_provider_url_ssl.py` | Git provider URL resolution, SSL handling |
| `test_api_discover_export.py` | Provider API interaction, discovery, export endpoints |
| `test_endpoint_lifecycle.py` | Analysis lifecycle state transitions, endpoint behavior |
| `test_output_templates.py` | Output rendering, template validation, export regressions |
| `test_security_headers_csrf.py` | Security headers, CSRF protection, CSP policies |
| `test_web_sse_health.py` | Web infrastructure, SSE streaming, health checks |
| `test_csp_defaults_caching.py` | CSP directives, default configuration, caching behavior |
| `test_i18n_sse_datetime.py` | Internationalization, SSE event formatting, datetime handling |
| `test_staleness_branding_schema.py` | Staleness detection, branding endpoints, schema validation |
| `test_milestone_labels_validation.py` | Milestone labels i18n, target year validation, order constraints |
| `test_header_buttons_url_focus.py` | Header company name, button styles, URL/slug field focus |
| `test_i18n.py` | Internationalization, locale loading |
| `test_release_calendar.py` | Release calendar utilities and validation |
| `test_release_pilot.py` | ReleasePilot integration adapter |
| `test_web.py` | FastAPI endpoints, API routes, SSE streaming |
| `test_web_calendar.py` | Web calendar endpoints |

### Integration Tests

| File | Coverage |
|:-----|:---------|
| `test_integration.py` | End-to-end: config to analysis to rendering |

## Test Style

All tests follow the **GIVEN/WHEN/THEN** pattern using docstring-based sections:

```python
def test_nonexistent_path(self, tmp_path: Path):
    """GIVEN a path that does not exist."""
    bad_path = str(tmp_path / "nonexistent")

    """WHEN inspecting the path."""
    result = inspect_repo(bad_path)

    """THEN it is not a valid repo."""
    assert result.is_valid_repo is False
    assert "does not exist" in result.error
```

Rules:

- `"""GIVEN ..."""` is the method docstring with setup code directly below
- `"""WHEN ..."""` is a string literal with the action code directly below
- `"""THEN ..."""` is a string literal with assertions directly below
- Every section must have code beneath it — no empty sections
- One blank line separates sections
- Each description ends with a period

> **Note:** Class-level docstrings use the `"""Scenarios for ..."""` format to describe the test group.

## Fixtures

Shared fixtures in `conftest.py`:

- **`sample_config`** — full `AppConfig` with 3 layers and 5 repos
- **`sample_config_dict`** — raw JSON dict for schema tests
- **`recent_branch_info`** — `BranchInfo` with today's date
- **`stale_branch_info`** — `BranchInfo` with old date
- **`tmp_config_file`** — config written to temp file

## Adding Tests

When adding new features:

1. Add tests for the behavior, not the implementation
2. Follow the GIVEN/WHEN/THEN pattern for every test method
3. Use the existing fixtures where possible
4. Prefer fewer, stronger tests over many trivial ones
5. Integration tests go in `test_integration.py`

> **Note:** Use descriptive test method names that convey intent. Naming convention: `test_<expected_outcome>_when_<condition>`.
