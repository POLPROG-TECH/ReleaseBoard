"""ReleasePilot integration — release preparation workflows for ReleaseBoard.

Provides a service adapter, data models, and validation for generating
release notes and preparing release artifacts from the ReleaseBoard dashboard.
"""

from releaseboard.integrations.releasepilot.adapter import ReleasePilotAdapter
from releaseboard.integrations.releasepilot.models import (
    SUPPORTED_LANGUAGES,
    AudienceMode,
    OutputFormat,
    ReleasePrepRequest,
    ReleasePrepResult,
    RepoContext,
)
from releaseboard.integrations.releasepilot.validation import validate_prep_request

__all__ = [
    "AudienceMode",
    "OutputFormat",
    "ReleasePilotAdapter",
    "ReleasePrepRequest",
    "ReleasePrepResult",
    "RepoContext",
    "SUPPORTED_LANGUAGES",
    "validate_prep_request",
]
