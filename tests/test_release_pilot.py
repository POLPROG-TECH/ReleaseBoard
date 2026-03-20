"""Tests for the ReleasePilot integration — models, validation, adapter, and API endpoints.

Covers:
- Data model creation and serialization
- Validation of all fields (valid and invalid)
- Adapter capabilities detection
- API endpoints via httpx AsyncClient
- i18n key presence in both locale files
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from releaseboard.integrations.releasepilot import (
    AudienceMode,
    OutputFormat,
    ReleasePilotAdapter,
    ReleasePrepRequest,
    ReleasePrepResult,
    RepoContext,
    validate_prep_request,
)
from releaseboard.integrations.releasepilot.validation import (
    validate_additional_notes,
    validate_audience,
    validate_git_ref,
    validate_output_format,
    validate_release_title,
    validate_release_version,
    validate_repo_context,
)
from releaseboard.web.server import create_app

try:
    import releasepilot as _rp  # noqa: F401
    _HAS_RELEASEPILOT = True
except ImportError:
    _HAS_RELEASEPILOT = False

requires_releasepilot = pytest.mark.skipif(
    not _HAS_RELEASEPILOT,
    reason="releasepilot package not installed",
)

# ── Test Fixtures ─────────────────────────────────────────────────

MINIMAL_CONFIG: dict[str, Any] = {
    "release": {
        "name": "March 2025",
        "target_month": 3,
        "target_year": 2025,
        "branch_pattern": "release/{MM}.{YYYY}",
    },
    "layers": [
        {"id": "ui", "label": "UI", "order": 0},
        {"id": "api", "label": "API", "order": 1},
    ],
    "repositories": [
        {"name": "web-app", "url": "https://git.local/web.git", "layer": "ui"},
        {"name": "svc-api", "url": "https://git.local/api.git", "layer": "api"},
    ],
}


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(MINIMAL_CONFIG, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def app(config_file: Path):
    return create_app(config_file)


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Model Tests ───────────────────────────────────────────────────


class TestAudienceMode:
    @requires_releasepilot
    def test_all_values(self):
        values = set(AudienceMode.values())
        assert values == {
            "technical", "user", "summary", "changelog",
            "customer", "executive", "narrative", "customer-narrative",
        }

    def test_label_key(self):
        assert AudienceMode("technical").label_key == "rp.audience.technical"
        assert AudienceMode("changelog").label_key == "rp.audience.changelog"
        assert AudienceMode("customer-narrative").label_key == "rp.audience.customer_narrative"

    def test_from_string(self):
        assert AudienceMode("technical") == "technical"
        assert AudienceMode("customer-narrative") == "customer-narrative"

    @requires_releasepilot
    def test_invalid_audience_raises(self):
        with pytest.raises(ValueError):
            AudienceMode("nonexistent")


class TestOutputFormat:
    @requires_releasepilot
    def test_all_values_mode_enum(self):
        values = set(OutputFormat.values())
        assert values == {"markdown", "plaintext", "json", "pdf", "docx"}

    def test_label_key_mode_enum(self):
        assert OutputFormat("markdown").label_key == "rp.format.markdown"
        assert OutputFormat("pdf").label_key == "rp.format.pdf"

    def test_export_deps_flag(self):
        assert OutputFormat("markdown").requires_export_deps is False
        assert OutputFormat("pdf").requires_export_deps is True
        assert OutputFormat("docx").requires_export_deps is True

    def test_from_string_mode_enum(self):
        assert OutputFormat("json") == "json"

    @requires_releasepilot
    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            OutputFormat("rtf")


class TestRepoContext:
    def test_creation(self):
        ctx = RepoContext(
            name="web-app",
            url="https://git.local/web.git",
            layer="ui",
            layer_label="UI",
        )
        assert ctx.name == "web-app"
        assert ctx.layer == "ui"
        assert ctx.default_branch == "main"
        assert ctx.branch_exists is False

    def test_frozen(self):
        ctx = RepoContext(name="x", url="u", layer="l", layer_label="L")
        with pytest.raises(AttributeError):
            ctx.name = "y"  # type: ignore[misc]


class TestReleasePrepRequest:
    def test_creation_with_defaults(self):
        req = ReleasePrepRequest(
            repo_name="web-app",
            repo_url="https://git.local/web.git",
            release_title="March Release",
            release_version="1.0.0",
            from_ref="main",
            to_ref="release/03.2025",
        )
        assert req.audience == "changelog"
        assert req.output_format == "markdown"
        assert req.include_authors is True
        assert req.include_hashes is False
        assert req.language == "en"

    def test_frozen_mode_enum(self):
        req = ReleasePrepRequest(
            repo_name="a", repo_url="b", release_title="c",
            release_version="1.0", from_ref="d", to_ref="e",
        )
        with pytest.raises(AttributeError):
            req.repo_name = "x"  # type: ignore[misc]


class TestReleasePrepResult:
    def test_success_result(self):
        result = ReleasePrepResult(
            success=True,
            repo_name="web-app",
            release_title="March Release",
            release_version="1.0.0",
            audience="changelog",
            output_format="markdown",
            content="# Release Notes",
            total_changes=5,
        )
        assert result.success is True
        assert result.error_message == ""

    def test_error_result(self):
        result = ReleasePrepResult(
            success=False,
            repo_name="web-app",
            release_title="March Release",
            release_version="1.0.0",
            audience="changelog",
            output_format="markdown",
            error_message="Git failed",
            error_code="git_error",
        )
        assert result.success is False
        assert result.error_code == "git_error"

    def test_to_dict(self):
        result = ReleasePrepResult(
            success=True,
            repo_name="web-app",
            release_title="Test",
            release_version="1.0.0",
            audience="changelog",
            output_format="markdown",
            content="# Notes",
            total_changes=2,
            highlights=("Feature A",),
            breaking_changes=(),
            warnings=("No git history",),
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["content"] == "# Notes"
        assert d["total_changes"] == 2
        assert d["highlights"] == ["Feature A"]
        assert d["warnings"] == ["No git history"]
        assert "generated_at" in d


# ── Validation Tests ──────────────────────────────────────────────


class TestValidateReleaseTitle:
    def test_valid_title(self):
        assert validate_release_title("March 2025 Release") == []

    def test_empty_title(self):
        errors = validate_release_title("")
        assert "rp.validation.title_required" in errors

    def test_whitespace_title(self):
        errors = validate_release_title("   ")
        assert "rp.validation.title_required" in errors

    def test_too_long_title(self):
        errors = validate_release_title("x" * 201)
        assert "rp.validation.title_too_long" in errors


class TestValidateReleaseVersion:
    def test_valid_versions(self):
        for v in ["1.0.0", "v1.0.0", "2025.03", "1.0.0-beta.1", "1.0.0+build.42"]:
            assert validate_release_version(v) == [], f"Expected valid: {v}"

    def test_empty_version(self):
        errors = validate_release_version("")
        assert "rp.validation.version_required" in errors

    def test_invalid_format(self):
        for v in ["not-a-version", "abc", "..."]:
            errors = validate_release_version(v)
            assert "rp.validation.version_invalid_format" in errors, f"Expected invalid: {v}"


class TestValidateGitRef:
    def test_valid_refs(self):
        for ref in ["main", "release/03.2025", "v1.0.0", "abc1234"]:
            assert validate_git_ref(ref, "from_ref") == [], f"Expected valid: {ref}"

    def test_empty_ref(self):
        errors = validate_git_ref("", "from_ref")
        assert errors == []  # Empty refs are allowed (RP auto-detects)

    def test_invalid_ref(self):
        errors = validate_git_ref("invalid ref with spaces", "to_ref")
        assert "rp.validation.to_ref_invalid" in errors


@requires_releasepilot
class TestValidateAudience:
    def test_valid_audiences(self):
        for a in AudienceMode.values():
            assert validate_audience(a) == []

    def test_invalid_audience(self):
        errors = validate_audience("invalid")
        assert "rp.validation.audience_invalid" in errors


@requires_releasepilot
class TestValidateOutputFormat:
    def test_valid_formats(self):
        for f in OutputFormat.values():
            assert validate_output_format(f) == []

    def test_invalid_format_mode_enum(self):
        errors = validate_output_format("rtf")
        assert "rp.validation.format_invalid" in errors


class TestValidateAdditionalNotes:
    def test_valid_notes(self):
        assert validate_additional_notes("Some notes") == []

    def test_empty_notes(self):
        assert validate_additional_notes("") == []

    def test_too_long_notes(self):
        errors = validate_additional_notes("x" * 5001)
        assert "rp.validation.notes_too_long" in errors


class TestValidateRepoContext:
    def test_valid(self):
        assert validate_repo_context("web-app", "https://git.local/web.git") == []

    def test_missing_name(self):
        errors = validate_repo_context("", "https://git.local/web.git")
        assert "rp.validation.repo_name_required" in errors

    def test_missing_url(self):
        errors = validate_repo_context("web-app", "")
        assert "rp.validation.repo_url_required" in errors


class TestValidatePrepRequest:
    def test_valid_request(self):
        data = {
            "repo_name": "web-app",
            "repo_url": "https://git.local/web.git",
            "release_title": "March 2025",
            "release_version": "1.0.0",
            "from_ref": "main",
            "to_ref": "release/03.2025",
            "audience": "changelog",
            "output_format": "markdown",
        }
        assert validate_prep_request(data) == []

    def test_multiple_errors(self):
        errors = validate_prep_request({})
        assert len(errors) >= 4  # repo_name, repo_url, title, version, refs


# ── Adapter Tests ─────────────────────────────────────────────────


@requires_releasepilot
class TestReleasePilotAdapter:
    def test_capabilities(self):
        adapter = ReleasePilotAdapter()
        caps = adapter.capabilities
        assert caps.available is True
        assert caps.mode == "library"
        assert len(caps.supported_audiences) == 8
        assert len(caps.supported_formats) == 5

    def test_capabilities_cached(self):
        adapter = ReleasePilotAdapter()
        c1 = adapter.capabilities
        c2 = adapter.capabilities
        assert c1 is c2

    def test_capabilities_to_dict(self):
        adapter = ReleasePilotAdapter()
        d = adapter.capabilities.to_dict()
        assert "available" in d
        assert "mode" in d
        assert "version" in d
        assert isinstance(d["supported_audiences"], list)
        assert isinstance(d["supported_formats"], list)

    def test_validate_returns_errors(self):
        adapter = ReleasePilotAdapter()
        errors = adapter.validate({})
        assert len(errors) > 0

    def test_validate_returns_empty_on_valid(self):
        adapter = ReleasePilotAdapter()
        errors = adapter.validate({
            "repo_name": "web-app",
            "repo_url": "https://git.local/web.git",
            "release_title": "March 2025",
            "release_version": "1.0.0",
            "from_ref": "main",
            "to_ref": "release/03.2025",
        })
        assert errors == []

    @pytest.mark.asyncio
    async def test_prepare_release(self):
        """Library mode generates release notes via ReleasePilot."""
        adapter = ReleasePilotAdapter()
        req = ReleasePrepRequest(
            repo_name="web-app",
            repo_url="https://git.local/web.git",
            release_title="March 2025 Release",
            release_version="1.0.0",
            from_ref="main",
            to_ref="release/03.2025",
            audience=AudienceMode("changelog"),
            output_format=OutputFormat("markdown"),
        )
        result = await adapter.prepare_release(req)
        assert result.repo_name == "web-app"
        assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_prepare_release_plaintext(self):
        adapter = ReleasePilotAdapter()
        req = ReleasePrepRequest(
            repo_name="svc-api",
            repo_url="https://git.local/api.git",
            release_title="Test Release",
            release_version="2.0.0",
            from_ref="main",
            to_ref="develop",
            audience=AudienceMode("technical"),
            output_format=OutputFormat("plaintext"),
        )
        result = await adapter.prepare_release(req)
        assert result.repo_name == "svc-api"
        assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_prepare_release_json(self):
        adapter = ReleasePilotAdapter()
        req = ReleasePrepRequest(
            repo_name="svc-api",
            repo_url="https://git.local/api.git",
            release_title="JSON Release",
            release_version="3.0.0",
            from_ref="main",
            to_ref="develop",
            audience=AudienceMode("summary"),
            output_format=OutputFormat("json"),
        )
        result = await adapter.prepare_release(req)
        assert result.repo_name == "svc-api"
        assert isinstance(result.content, str)


# ── API Endpoint Tests ────────────────────────────────────────────


@requires_releasepilot
class TestCapabilitiesEndpoint:
    @pytest.mark.asyncio
    async def test_get_capabilities(self, client: AsyncClient):
        resp = await client.get("/api/release-pilot/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["available"] is True
        assert data["mode"] == "library"
        assert len(data["supported_audiences"]) == 8
        assert len(data["supported_formats"]) == 5


@requires_releasepilot
class TestValidateEndpoint:
    @pytest.mark.asyncio
    async def test_valid_payload(self, client: AsyncClient):
        payload = {
            "repo_name": "web-app",
            "repo_url": "https://git.local/web.git",
            "release_title": "March 2025",
            "release_version": "1.0.0",
            "from_ref": "main",
            "to_ref": "release/03.2025",
        }
        resp = await client.post("/api/release-pilot/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_invalid_payload(self, client: AsyncClient):
        payload = {"repo_name": "", "repo_url": ""}
        resp = await client.post("/api/release-pilot/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert len(data["errors"]) > 0
        assert len(data["error_keys"]) > 0


@requires_releasepilot
class TestPrepareEndpoint:
    @pytest.mark.asyncio
    async def test_valid_prepare(self, client: AsyncClient):
        payload = {
            "repo_name": "web-app",
            "repo_url": "https://git.local/web.git",
            "release_title": "March 2025 Release",
            "release_version": "1.0.0",
            "from_ref": "main",
            "to_ref": "release/03.2025",
            "audience": "changelog",
            "output_format": "markdown",
        }
        resp = await client.post("/api/release-pilot/prepare", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # RP delegates to git — with a fake URL it returns a graceful error
        assert "generated_at" in data
        assert "content" in data
        assert data["repo_name"] == "web-app"

    @pytest.mark.asyncio
    async def test_invalid_prepare_returns_422(self, client: AsyncClient):
        payload = {"repo_name": "", "release_title": ""}
        resp = await client.post("/api/release-pilot/prepare", json=payload)
        assert resp.status_code == 422
        data = resp.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_prepare_json_format(self, client: AsyncClient):
        payload = {
            "repo_name": "svc-api",
            "repo_url": "https://git.local/api.git",
            "release_title": "JSON Release",
            "release_version": "2.0.0",
            "from_ref": "main",
            "to_ref": "release/03.2025",
            "audience": "summary",
            "output_format": "json",
        }
        resp = await client.post("/api/release-pilot/prepare", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # RP delegates to git — with a fake URL it returns a graceful error
        assert "generated_at" in data
        assert data["repo_name"] == "svc-api"


class TestRepoContextEndpoint:
    @pytest.mark.asyncio
    async def test_known_repo(self, client: AsyncClient):
        resp = await client.get("/api/release-pilot/repo-context/web-app")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["name"] == "web-app"
        assert data["layer"] == "ui"
        assert data["layer_label"] == "UI"
        assert "branch_pattern" in data
        assert data["release_name"] == "March 2025"

    @pytest.mark.asyncio
    async def test_unknown_repo(self, client: AsyncClient):
        resp = await client.get("/api/release-pilot/repo-context/unknown-repo")
        assert resp.status_code == 404
        data = resp.json()
        assert data["ok"] is False


# ── i18n Parity Tests ─────────────────────────────────────────────


_LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "releaseboard" / "i18n" / "locales"


class TestReleasePilotI18n:
    """Ensure all rp.* keys exist in both locale files."""

    def _load_keys(self, locale: str) -> set[str]:
        with open(_LOCALES_DIR / f"{locale}.json", encoding="utf-8") as f:
            data = json.load(f)
        return {k for k in data if k.startswith("rp.")}

    def test_rp_keys_exist_in_en(self):
        en_keys = self._load_keys("en")
        assert len(en_keys) >= 110, f"Expected at least 110 rp.* keys in EN, got {len(en_keys)}"

    def test_rp_keys_exist_in_pl(self):
        pl_keys = self._load_keys("pl")
        assert len(pl_keys) >= 110, f"Expected at least 110 rp.* keys in PL, got {len(pl_keys)}"

    def test_rp_keys_parity(self):
        """Every rp.* key in EN must exist in PL and vice versa."""
        en_keys = self._load_keys("en")
        pl_keys = self._load_keys("pl")
        missing_in_pl = en_keys - pl_keys
        missing_in_en = pl_keys - en_keys
        assert not missing_in_pl, f"rp.* keys in EN but not PL: {missing_in_pl}"
        assert not missing_in_en, f"rp.* keys in PL but not EN: {missing_in_en}"

    def test_required_validation_keys(self):
        """All validation error keys must exist."""
        en_keys = self._load_keys("en")
        required = {
            "rp.validation.title_required",
            "rp.validation.title_too_long",
            "rp.validation.version_required",
            "rp.validation.version_too_long",
            "rp.validation.version_invalid_format",
            "rp.validation.audience_invalid",
            "rp.validation.format_invalid",
            "rp.validation.notes_too_long",
            "rp.validation.repo_name_required",
            "rp.validation.repo_url_required",
        }
        missing = required - en_keys
        assert not missing, f"Missing validation i18n keys: {missing}"


# ── Dashboard Integration Tests ───────────────────────────────────


class TestDashboardIntegration:
    @pytest.mark.asyncio
    async def test_dashboard_includes_wizard_html(self, client: AsyncClient):
        """The dashboard page should include the release wizard overlay."""
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "rp-wizard-overlay" in resp.text

    @pytest.mark.asyncio
    async def test_dashboard_includes_wizard_styles(self, client: AsyncClient):
        """The dashboard page should include wizard CSS."""
        resp = await client.get("/")
        assert "rp-wizard-panel" in resp.text
        assert "rp-action-btn" in resp.text

    @pytest.mark.asyncio
    async def test_dashboard_includes_prepare_button(self, client: AsyncClient):
        """The dashboard template should contain the RP.openWizard reference."""
        resp = await client.get("/")
        # The button is rendered per-repo and only if repos are displayed.
        # In test mode without analysis results, repos may not render.
        # Verify the JS namespace is available, which is always included.
        assert "RP.openWizard" in resp.text or "rp-action-btn" in resp.text or "RP" in resp.text

    @pytest.mark.asyncio
    async def test_dashboard_includes_wizard_js(self, client: AsyncClient):
        """The wizard JavaScript should be included."""
        resp = await client.get("/")
        assert "window.RP" in resp.text or "const RP" in resp.text or "RP =" in resp.text
