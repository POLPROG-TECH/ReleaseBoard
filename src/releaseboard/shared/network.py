"""Shared networking utilities — SSL context, auth URL injection, HTTP helpers.

This module centralises corporate-network concerns (proxy CAs, Zscaler,
custom cert bundles) so that *every* outgoing HTTPS call — git providers,
integrations, webhooks — uses the same trusted SSL context.

Usage::

    from releaseboard.shared.network import make_ssl_context, inject_token_into_url

Functions
---------
make_ssl_context
    Build an ``ssl.SSLContext`` that honours corporate CA bundles.
inject_token_into_url
    Embed a token into an HTTPS URL (GitHub / GitLab convention).
http_get_json
    One-shot GET with retry, SSL context, and structured error dict.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSL / TLS
# ---------------------------------------------------------------------------

_cached_ssl_ctx: ssl.SSLContext | None = None


def make_ssl_context(*, force_new: bool = False) -> ssl.SSLContext:
    """Build an SSL context that works in corporate proxy environments.

    Resolution order:

    1. ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` env var (explicit override)
    2. ``certifi`` package (ships Mozilla CA bundle)
    3. macOS system keychain (includes corporate CAs like Zscaler)
    4. Python default (works on most Linux distros)

    The result is cached process-wide (thread-safe for reads) unless
    *force_new* is True.
    """
    global _cached_ssl_ctx
    if _cached_ssl_ctx is not None and not force_new:
        return _cached_ssl_ctx

    ctx = _build_ssl_context()
    _cached_ssl_ctx = ctx
    return ctx


def _build_ssl_context() -> ssl.SSLContext:
    """Internal builder — not cached, always creates a fresh context."""
    # 1. Honour explicit env var
    for env in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        ca = os.environ.get(env)
        if ca and os.path.isfile(ca):
            logger.debug("SSL: using CA bundle from %s=%s", env, ca)
            return ssl.create_default_context(cafile=ca)

    # 2. Try certifi
    try:
        import certifi

        logger.debug("SSL: using certifi CA bundle")
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    # 3. Try macOS system certificates (includes corporate CAs)
    try:
        import subprocess

        pem = subprocess.run(
            [
                "security",
                "find-certificate",
                "-a",
                "-p",
                "/Library/Keychains/System.keychain",
                "/System/Library/Keychains/SystemRootCertificates.keychain",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pem.returncode == 0 and "BEGIN CERTIFICATE" in pem.stdout:
            ctx = ssl.create_default_context()
            ctx.load_verify_locations(cadata=pem.stdout)
            logger.debug("SSL: loaded macOS system certificates")
            return ctx
    except Exception:
        pass

    # 4. Default
    logger.debug("SSL: using Python default context")
    return ssl.create_default_context()


# ---------------------------------------------------------------------------
# Auth URL injection
# ---------------------------------------------------------------------------


def inject_token_into_url(url: str, token: str, *, provider: str = "auto") -> str:
    """Embed *token* into an HTTPS URL for authenticated git access.

    Parameters
    ----------
    url:
        Repository or API URL (``https://...``).
    token:
        Personal access token / OAuth token.
    provider:
        ``"github"``, ``"gitlab"``, or ``"auto"`` (detect from hostname).

        - GitHub:  ``https://<token>@github.com/…``
        - GitLab:  ``https://oauth2:<token>@gitlab.example.com/…``

    Returns the original *url* unchanged when *token* is empty or the
    scheme is not HTTP(S).
    """
    if not token:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return url
    if not parsed.hostname:
        return url

    if provider == "auto":
        provider = "github" if "github" in (parsed.hostname or "").lower() else "gitlab"

    if provider == "github":
        netloc = f"{token}@{parsed.hostname}"
    else:
        netloc = f"oauth2:{token}@{parsed.hostname}"

    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


# ---------------------------------------------------------------------------
# HTTP GET helper with retry
# ---------------------------------------------------------------------------

# Transient HTTP status codes worth retrying
_TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 2,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[Any, int]:
    """GET *url* and return ``(parsed_json, http_status)``.

    - Returns ``(None, 0)`` on network-level failures (DNS, SSL, timeout).
    - Retries up to *retries* times on 502/503/504 or network errors,
      with exponential back-off (0.5 s × 2^attempt).
    - Uses :func:`make_ssl_context` by default.
    """
    ctx = ssl_context or make_ssl_context()
    all_headers = {"Accept": "application/json"}
    if headers:
        all_headers.update(headers)

    last_data: Any = None
    last_status = 0

    for attempt in range(1 + retries):
        req = urllib.request.Request(url, headers=all_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode()), resp.status
        except urllib.error.HTTPError as exc:
            logger.debug("HTTP %d for %s: %s", exc.code, url, exc.reason)
            try:
                body = json.loads(exc.read().decode())
                last_data, last_status = body, exc.code
            except Exception:
                last_data, last_status = None, exc.code
            if exc.code in _TRANSIENT_STATUS_CODES and attempt < retries:
                time.sleep(0.5 * (2**attempt))
                continue
            return last_data, last_status
        except Exception as exc:
            logger.debug("Request failed for %s: %s", url, exc)
            last_data, last_status = None, 0
            if attempt < retries:
                time.sleep(0.5 * (2**attempt))
                continue
            return last_data, last_status

    return last_data, last_status

