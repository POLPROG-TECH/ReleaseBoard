# ReleasePilot Integration

ReleaseBoard is designed to work together with [ReleasePilot](https://github.com/polprog-tech/ReleasePilot/blob/main/README.md) — release note generation library. Together they form a complete release management toolkit: **ReleaseBoard** handles readiness tracking and dashboard visualization, while **ReleasePilot** generates structured release notes from Git history.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [How It Works](#how-it-works)
- [Audiences](#audiences)
- [Output Formats](#output-formats)
- [API Reference](#api-reference)
- [Configuration](#configuration)

## Overview

When ReleasePilot is installed alongside ReleaseBoard, a release-note wizard becomes available in the dashboard. This wizard allows you to generate, preview, edit, and export release notes — all without leaving the ReleaseBoard UI.

The integration is **optional**. ReleaseBoard functions fully without ReleasePilot; the release-note wizard simply won't appear.

## Installation

```bash
# Install from the official GitHub repository (recommended)
pip install "releasepilot @ git+https://github.com/polprog-tech/ReleasePilot.git"

# Or install ReleaseBoard with ReleasePilot included
pip install -e ".[releasepilot]"

# Verify the integration is detected
releaseboard version
```

ReleaseBoard auto-detects ReleasePilot at runtime. No configuration changes are needed.

## Dependency Model

ReleasePilot is an **optional external dependency**. ReleaseBoard integrates with it through a clean adapter pattern:

- **Default**: ReleaseBoard works fully without ReleasePilot. The release-note wizard simply doesn't appear.
- **Remote (recommended)**: Install from the official GitHub repository: `pip install "releasepilot @ git+https://github.com/polprog-tech/ReleasePilot.git"`
- **Bundled install**: Use `pip install "releaseboard[releasepilot]"` to install both together.
- **Local development**: If you're developing ReleasePilot alongside ReleaseBoard, you can use an editable install: `pip install -e /path/to/ReleasePilot`

The adapter auto-detects ReleasePilot at runtime via conditional imports. No configuration changes are needed — if the package is importable, the wizard becomes available.

> **Note:** A manual local clone is NOT required. The default integration uses the public GitHub repository as the source.

## How It Works

```
┌─────────────────────────────────────────────────┐
│                  ReleaseBoard                    │
│                                                  │
│  Dashboard  ──►  Release Prep Wizard             │
│                       │                          │
│                       ▼                          │
│              ReleasePilotAdapter                  │
│                       │                          │
│                       ▼                          │
│              ┌────────────────┐                  │
│              │  ReleasePilot  │  (external lib)  │
│              └────────────────┘                  │
│                       │                          │
│                       ▼                          │
│              Generated Release Notes             │
│              (Markdown / JSON / PDF / DOCX)      │
└─────────────────────────────────────────────────┘
```

1. **User opens the wizard** from the dashboard toolbar
2. **Fills in release details** — title, version, Git ref range, audience, format
3. **ReleaseBoard validates** the request via `validate_prep_request()`
4. **ReleasePilotAdapter** forwards the request to the ReleasePilot library
5. **Generated notes** are returned for preview, editing, and download

## Audiences

ReleasePilot supports multiple audience modes for tailored release notes:

| Audience | Key | Description |
|:---------|:----|:------------|
| Technical | `technical` | Detailed changes for developers |
| Executive | `executive` | High-level summary for leadership |
| Customer | `customer` | User-facing changes and improvements |
| Changelog | `changelog` | Structured changelog format |
| Summary | `summary` | Brief overview of all changes |
| Narrative | `narrative` | Story-form release announcement |
| Customer Narrative | `customer-narrative` | Customer-facing story format |

Each audience mode has an i18n key (`rp.audience.<mode>`) for localized labels.

## Output Formats

| Format | Key | Description |
|:-------|:----|:------------|
| Markdown | `markdown` | Standard Markdown output |
| Plain Text | `plaintext` | Plain text without formatting |
| JSON | `json` | Structured JSON data |
| PDF | `pdf` | Portable Document Format |
| DOCX | `docx` | Microsoft Word document |

## API Reference

### Models

```python
from releaseboard.integrations.releasepilot import (
    AudienceMode,
    OutputFormat,
    ReleasePrepRequest,
    ReleasePrepResult,
    RepoContext,
)
```

**`RepoContext`** — repository information for note generation:
- `name` — repository display name
- `url` — repository URL
- `branch` — target branch

**`ReleasePrepRequest`** — full request to generate notes:
- `title` — release title
- `version` — release version string
- `git_ref_from` / `git_ref_to` — commit range
- `audience` — target audience mode
- `output_format` — desired output format
- `repos` — list of `RepoContext` objects
- `additional_notes` — optional extra context

**`ReleasePrepResult`** — generated output:
- `content` — generated release notes
- `format` — output format used
- `audience` — audience mode used

### Validation

```python
from releaseboard.integrations.releasepilot.validation import validate_prep_request

errors = validate_prep_request(request)
# Returns list of validation error strings, empty if valid
```

Individual validators are also available:
- `validate_release_title(title)`
- `validate_release_version(version)`
- `validate_git_ref(ref)`
- `validate_output_format(fmt)`
- `validate_audience(audience)`
- `validate_additional_notes(notes)`
- `validate_repo_context(repo)`

### Adapter

```python
from releaseboard.integrations.releasepilot import ReleasePilotAdapter

adapter = ReleasePilotAdapter()
available = adapter.is_available()  # True if ReleasePilot is installed
```

## Configuration

No special configuration is needed. ReleasePilot is auto-detected at runtime via conditional imports — see the [Dependency Model](#dependency-model) section above.

To customize ReleasePilot behavior, refer to the [ReleasePilot documentation](https://github.com/polprog-tech/ReleasePilot/blob/main/README.md).
