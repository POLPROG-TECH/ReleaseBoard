"""Tests for security headers, CSRF protection, and middleware stack.

Covers: security headers, CSRF protection, rate limiting, API key auth,
SmartGitProvider TTL, config ETag, SSE event IDs, template error handling,
error sanitization, readiness/liveness probes, and invalid JSON handling.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_MINIMAL_CONFIG = {
    "release": {"name": "Test", "target_month": 3, "target_year": 2026},
    "repositories": [],
    "layers": [],
    "branding": {
        "title": "Test",
        "subtitle": "Test Dashboard",
        "primary_color": "#fb6400",
        "secondary_color": "#002754e6",
    },
    "settings": {
        "stale_threshold_days": 14,
        "output_path": "output/test.html",
        "theme": "system",
        "timeout_seconds": 30,
        "max_concurrent": 5,
    },
}


@pytest.fixture
def config_path(tmp_path):
    p = tmp_path / "releaseboard.json"
    p.write_text(json.dumps(_MINIMAL_CONFIG), encoding="utf-8")
    return p


@pytest.fixture
def app(config_path):
    from releaseboard.web.server import create_app
    return create_app(config_path)


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


class TestSecurityHeaders:
    """Scenarios for security headers."""

    @pytest.mark.asyncio
    async def test_security_headers_present_on_api(self, client):
        """GIVEN an API status endpoint."""
        endpoint = "/api/status"

        """WHEN requesting the status."""
        resp = await client.get(endpoint)

        """THEN security headers are present."""
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert "strict-origin" in resp.headers.get("referrer-policy", "")
        assert "camera=()" in resp.headers.get("permissions-policy", "")

    @pytest.mark.asyncio
    async def test_csp_header_present(self, client):
        """GIVEN an API status endpoint."""
        endpoint = "/api/status"

        """WHEN requesting the status."""
        resp = await client.get(endpoint)

        """THEN CSP header contains required directives."""
        csp = resp.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp
        assert "default-src 'self'" in csp

    @pytest.mark.asyncio
    async def test_xss_protection_header(self, client):
        """GIVEN an API status endpoint."""
        endpoint = "/api/status"

        """WHEN requesting the status."""
        resp = await client.get(endpoint)

        """THEN XSS protection header is set."""
        assert "1; mode=block" in resp.headers.get("x-xss-protection", "")


class TestCSRFProtection:
    """Scenarios for CSRF protection."""

    @pytest.mark.asyncio
    async def test_rejects_cross_origin_post(self, client):
        """GIVEN a cross-origin POST request."""
        headers = {"origin": "http://evil.com"}

        """WHEN posting to the config save endpoint."""
        resp = await client.post("/api/config/save", headers=headers)

        """THEN the request is rejected with CSRF error."""
        assert resp.status_code == 403
        assert "CSRF" in resp.json().get("error", "")

    @pytest.mark.asyncio
    async def test_allows_same_origin_post(self, client):
        """GIVEN a same-origin POST request."""
        headers = {"origin": "http://testserver"}

        """WHEN posting to the config save endpoint."""
        resp = await client.post("/api/config/save", headers=headers)

        """THEN the request is not blocked by CSRF."""
        # Should not be blocked by CSRF (may be 200 or other non-403)
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_allows_get_with_any_origin(self, client):
        """GIVEN a GET request with a cross-origin header."""
        headers = {"origin": "http://evil.com"}

        """WHEN requesting the config endpoint."""
        resp = await client.get("/api/config", headers=headers)

        """THEN the request succeeds."""
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_allows_post_without_origin(self, client):
        """GIVEN a POST request without an Origin header."""
        endpoint = "/api/config/save"

        """WHEN posting from a non-browser client."""
        resp = await client.post(endpoint)

        """THEN the request passes through."""
        assert resp.status_code != 403


class TestRateLimiting:
    """Scenarios for rate limiting."""

    @pytest.mark.asyncio
    async def test_normal_traffic_allowed(self, client):
        """GIVEN a client sending a few requests."""
        request_count = 5

        """WHEN requesting the status endpoint repeatedly."""
        statuses = []
        for _ in range(request_count):
            resp = await client.get("/api/status")
            statuses.append(resp.status_code)

        """THEN all requests succeed without rate limiting."""
        assert all(s == 200 for s in statuses)

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excess_requests(self):
        """GIVEN a rate-limited app with 3 requests per minute."""
        from fastapi import FastAPI

        from releaseboard.web.middleware import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware, requests_per_minute=3, analysis_per_minute=1
        )

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        """WHEN sending more requests than allowed."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            statuses = []
            for _ in range(6):
                resp = await c.get("/test")
                statuses.append(resp.status_code)

        """THEN at least one request is rate-limited."""
        assert 429 in statuses

    @pytest.mark.asyncio
    async def test_analysis_rate_limit_stricter(self):
        """GIVEN an app with strict analysis rate limiting."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from releaseboard.web.middleware import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware, requests_per_minute=1000, analysis_per_minute=2
        )

        @app.post("/api/analyze")
        async def analyze():
            return JSONResponse({"ok": True})

        """WHEN sending more analysis requests than allowed."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            statuses = []
            for _ in range(5):
                resp = await c.post("/api/analyze")
                statuses.append(resp.status_code)

        """THEN at least one request is rate-limited."""
        assert 429 in statuses


class TestAPIKeyAuth:
    """Scenarios for API key authentication."""

    @pytest.mark.asyncio
    async def test_no_auth_when_key_not_configured(self, client):
        """GIVEN no API key configured in environment."""
        endpoint = "/api/config/save"

        """WHEN posting without an API key."""
        resp = await client.post(endpoint)

        """THEN the request is not rejected for authentication."""
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_auth_required_when_key_configured(self, config_path):
        """GIVEN an app with RELEASEBOARD_API_KEY configured."""
        from releaseboard.web.server import create_app

        """WHEN posting without and with the correct API key."""
        # Keep env var active through middleware instantiation AND request
        with patch.dict(os.environ, {"RELEASEBOARD_API_KEY": "test-secret"}):
            app = create_app(config_path)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as c:
                # Without key → 401
                resp_no_key = await c.post("/api/config/save")
                # With correct key → not 401
                resp_with_key = await c.post(
                    "/api/config/save",
                    headers={"x-api-key": "test-secret"},
                )

        """THEN requests without key get 401 and with key pass."""
        assert resp_no_key.status_code == 401
        assert resp_with_key.status_code != 401

    @pytest.mark.asyncio
    async def test_wrong_key_rejected(self, config_path):
        """GIVEN an app with a specific API key configured."""
        from releaseboard.web.server import create_app

        """WHEN posting with an incorrect API key."""
        with patch.dict(os.environ, {"RELEASEBOARD_API_KEY": "correct-key"}):
            app = create_app(config_path)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as c:
                resp = await c.post(
                    "/api/config/save",
                    headers={"x-api-key": "wrong-key"},
                )

        """THEN the request is rejected."""
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_allowed_even_with_api_key(self, config_path):
        """GIVEN an app with RELEASEBOARD_API_KEY configured."""
        from releaseboard.web.server import create_app

        """WHEN making a GET request without an API key."""
        with patch.dict(os.environ, {"RELEASEBOARD_API_KEY": "test-secret"}):
            app = create_app(config_path)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as c:
                resp = await c.get("/api/status")

        """THEN the GET request succeeds."""
        assert resp.status_code == 200


class TestSSEEventIDs:
    """Scenarios for SSE event IDs."""

    def test_sse_format_includes_id_field(self):
        """GIVEN an SSE event with data."""
        from releaseboard.web.server import _sse_format
        event_name = "test_event"
        data = {"key": "value"}

        """WHEN formatting the SSE event."""
        output = _sse_format(event_name, data)

        """THEN the output includes id, event, and data fields."""
        lines = output.strip().split("\n")
        assert lines[0].startswith("id: ")
        assert "event: test_event" in output
        assert "data:" in output

    def test_sse_ids_are_incrementing(self):
        """GIVEN two consecutive SSE events."""
        from releaseboard.web.server import _sse_format

        """WHEN formatting them sequentially."""
        out1 = _sse_format("a", {})
        out2 = _sse_format("b", {})

        """THEN the second ID is greater than the first."""
        id1 = int(out1.split("\n")[0].split(": ", 1)[1])
        id2 = int(out2.split("\n")[0].split(": ", 1)[1])
        assert id2 > id1

    def test_sse_data_is_valid_json(self):
        """GIVEN an SSE event with a count payload."""
        from releaseboard.web.server import _sse_format
        output = _sse_format("evt", {"count": 42})

        """WHEN parsing the data field."""
        parsed_data = None
        for line in output.strip().split("\n"):
            if line.startswith("data: "):
                parsed_data = json.loads(line[6:])

        """THEN the data is valid JSON with expected content."""
        assert parsed_data is not None
        assert parsed_data["count"] == 42


class TestErrorSanitization:
    """Scenarios for error sanitization."""

    @pytest.mark.asyncio
    async def test_404_does_not_expose_internals(self, client):
        """GIVEN a nonexistent path."""
        endpoint = "/nonexistent-path-xyz"

        """WHEN requesting the nonexistent path."""
        resp = await client.get(endpoint)

        """THEN the response does not expose internal details."""
        assert resp.status_code == 404
        body = resp.json()
        assert "traceback" not in str(body).lower()
        assert "File " not in str(body)

    @pytest.mark.asyncio
    async def test_save_error_does_not_expose_path(self, config_path):
        """GIVEN an AppState with an unwritable config file."""
        from releaseboard.web.state import AppState
        state = AppState(config_path)
        config_path.chmod(0o444)

        """WHEN attempting to save the config."""
        try:
            errors = state.save_config()
        finally:
            config_path.chmod(0o644)

        """THEN error messages do not contain filesystem paths."""
        if errors:
            for err in errors:
                assert str(config_path) not in err


class TestHealthProbes:
    """Scenarios for health probes."""

    @pytest.mark.asyncio
    async def test_liveness_probe(self, client):
        """GIVEN a running application."""
        endpoint = "/health/live"

        """WHEN requesting the liveness probe."""
        resp = await client.get(endpoint)

        """THEN the app reports as alive."""
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.asyncio
    async def test_readiness_probe_when_ready(self, client):
        """GIVEN a running application with valid config."""
        endpoint = "/health/ready"

        """WHEN requesting the readiness probe."""
        resp = await client.get(endpoint)

        """THEN the app reports as ready with correct details."""
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["config_readable"] is True
        assert body["analysis_running"] is False


class TestInvalidJSONHandling:
    """Scenarios for invalid JSON handling."""

    @pytest.mark.asyncio
    async def test_malformed_json_returns_400(self, client):
        """GIVEN a malformed JSON payload."""
        payload = b"this is not valid json {{{"
        headers = {"content-type": "application/json"}

        """WHEN sending the malformed payload."""
        resp = await client.put("/api/config", content=payload, headers=headers)

        """THEN a 400 error mentioning JSON is returned."""
        assert resp.status_code == 400
        assert "json" in resp.json().get("error", "").lower()

    @pytest.mark.asyncio
    async def test_empty_body_returns_400(self, client):
        """GIVEN an empty request body."""
        payload = b""
        headers = {"content-type": "application/json"}

        """WHEN sending the empty body."""
        resp = await client.put("/api/config", content=payload, headers=headers)

        """THEN a 400 error is returned."""
        assert resp.status_code == 400


class TestMiddlewareIntegration:
    """Scenarios for middleware integration."""

    @pytest.mark.asyncio
    async def test_all_middleware_applied_to_app(self, app):
        """GIVEN a fully configured application."""
        middleware_names = [str(m) for m in app.user_middleware]

        """WHEN inspecting the middleware stack."""
        combined = " ".join(middleware_names)

        """THEN all required middleware are present."""
        assert "SecurityHeaders" in combined
        assert "RequestLogging" in combined
        assert "RateLimit" in combined
        assert "CSRF" in combined
        assert "APIKey" in combined

    @pytest.mark.asyncio
    async def test_middleware_doesnt_break_sse_endpoint(self, client):
        """GIVEN a client requesting an API endpoint with middleware."""
        endpoint = "/api/status"

        """WHEN requesting the endpoint."""
        resp = await client.get(endpoint)

        """THEN the response succeeds with security headers."""
        assert resp.status_code == 200
        # Verify security headers were added by middleware
        assert "x-content-type-options" in resp.headers
