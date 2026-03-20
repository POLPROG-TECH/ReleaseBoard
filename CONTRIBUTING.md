# Contributing to ReleaseBoard

Thank you for your interest in contributing to ReleaseBoard! This guide covers everything you need to get started.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Quality](#code-quality)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features](#suggesting-features)
  - [Pull Requests](#pull-requests)
- [Commit Message Convention](#commit-message-convention)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [License](#license)

## Development Setup

Clone the repository and install in development mode:

```bash
git clone <repo-url> && cd ReleaseBoard
pip install -e ".[dev]"
```

Verify the installation:

```bash
releaseboard version
```

### Install the pre-commit hook

A pre-commit hook runs lint and tests automatically before each commit:

```bash
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

## Running Tests

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# With coverage report
pytest --cov=releaseboard --cov-report=term-missing

# Run a specific test file
pytest tests/test_config.py

# Run a specific test case
pytest tests/test_config.py::TestBranchPatternOverrides::test_layer_override_takes_precedence
```

> **Note:** Tests follow the GIVEN/WHEN/THEN pattern where it adds clarity. See [docs/testing.md](docs/testing.md) for the full testing guide.

## Code Quality

Run the linter before submitting changes:

```bash
ruff check src/ tests/
```

ReleaseBoard uses `ruff` for both linting and formatting. Ensure all checks pass before opening a pull request.

## How to Contribute

### Reporting Bugs

When reporting a bug, please include:

- **Expected vs actual behavior** — describe what you expected and what happened
- **Configuration** — include your `releaseboard.json` (redact URLs and tokens)
- **Environment** — Python version, OS, and ReleaseBoard version (`releaseboard version`)
- **Steps to reproduce** — minimal steps to trigger the issue

### Suggesting Features

Feature suggestions are welcome. Please include:

- **Use case** — describe the problem you are trying to solve
- **Proposed solution** — how you envision the feature working
- **Alternatives** — any alternative approaches you have considered

### Pull Requests

1. Create a feature branch from `main`
2. Make your changes
3. Add or update tests as needed
4. Run the full test suite: `pytest`
5. Run the linter: `ruff check src/ tests/`
6. Ensure all checks pass
7. Open a pull request with a clear description

> **Note:** See [docs/architecture.md](docs/architecture.md) for the layered architecture. Key rules: the domain layer has no external dependencies, git access goes through the `GitProvider` abstraction, presentation uses view models (not domain objects directly), and config is validated by JSON Schema before use.

## Commit Message Convention

ReleaseBoard follows the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```text
<type>: <short description>

[optional body]
```

| Type | Description |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation changes |
| `test` | Adding or updating tests |
| `refactor` | Code restructuring without behavior change |
| `chore` | Build scripts, CI, dependencies, tooling |

**Examples:**

```text
feat: add GitLab provider support
fix: correct stale threshold calculation for UTC offsets
docs: update configuration reference for layout templates
test: add coverage for three-tier branch pattern override
refactor: extract error classification into dedicated module
chore: upgrade ruff to 0.5.x
```

## Project Structure

```text
src/releaseboard/
├── __init__.py
├── analysis/                  # Business logic for readiness evaluation
│   ├── branch_pattern.py      # Pattern resolution and regex matching
│   ├── metrics.py             # Per-layer and global metrics aggregation
│   ├── readiness.py           # Readiness status evaluation
│   └── staleness.py           # Branch staleness detection
├── application/               # Shared orchestration (CLI + web)
│   └── service.py             # AnalysisService pipeline
├── calendar/                  # Release calendar utilities
│   └── validator.py           # Calendar validation
├── cli/                       # User-facing entry point
│   └── app.py                 # Typer commands: generate, serve, validate, version
├── config/                    # Configuration loading and validation
│   ├── loader.py              # JSON loading, env var resolution, typed config
│   ├── models.py              # Typed dataclass config models
│   ├── schema.json            # JSON Schema (Draft 7)
│   └── schema.py              # Schema validation via jsonschema
├── domain/                    # Pure data models (zero dependencies)
│   ├── enums.py               # ReadinessStatus, GitErrorKind
│   └── models.py              # BranchInfo, RepositoryAnalysis, LayerDefinition
├── git/                       # Abstracted repository access
│   ├── github_provider.py     # GitHub REST API provider
│   ├── gitlab_provider.py     # GitLab API provider
│   ├── local_provider.py      # Local git CLI provider
│   ├── provider.py            # Abstract GitProvider base class
│   └── smart_provider.py      # Auto-selecting provider
├── i18n/                      # Internationalization
│   └── locales/               # Locale files (en.json, pl.json)
├── integrations/              # Third-party integrations
│   └── releasepilot/          # ReleasePilot adapter
├── presentation/              # View models and HTML rendering
│   ├── renderer.py            # Jinja2-based HTML generation
│   ├── templates/             # HTML templates (dashboard, partials)
│   ├── theme.py               # Enterprise visual design and color palette
│   └── view_models.py         # Domain-to-presentation conversion
├── shared/                    # Cross-cutting concerns
│   ├── logging.py             # Logging configuration
│   └── types.py               # Type aliases
└── web/                       # FastAPI interactive web layer
    ├── middleware.py           # HTTP middleware
    ├── server.py              # FastAPI application factory (API routes)
    └── state.py               # Three-tier config state, SSE subscribers
```

## Code Style

- **Python 3.12+** with full type hints
- **Formatted with `ruff`** — linting and formatting
- **Tests use `pytest`** with GIVEN/WHEN/THEN structure where helpful
- **Behavior-oriented tests** — test what the code does, not how it does it
- **Domain layer purity** — no external dependencies in `domain/`
- **View model separation** — presentation never receives domain objects directly

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.
