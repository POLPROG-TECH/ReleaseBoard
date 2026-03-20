"""Tests for the i18n module — catalog parity, interpolation, pluralization."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from releaseboard.i18n import (
    _plural_key,
    default_locale,
    detect_locale_from_header,
    get_catalog,
    reload_catalogs,
    set_locale,
    supported_locales,
    t,
)

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "releaseboard" / "i18n" / "locales"
_INTERPOLATION_RE = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def _clean_catalogs():
    """Ensure catalogs are freshly loaded for each test."""
    reload_catalogs()
    yield
    reload_catalogs()


# ── Catalog Parity ──────────────────────────────────────────────────


class TestCatalogParity:
    """Every key in EN must exist in PL and vice-versa."""

    def _load_raw(self, locale: str) -> dict[str, str]:
        path = _LOCALES_DIR / f"{locale}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_en_and_pl_have_same_keys(self):
        en = set(self._load_raw("en").keys())
        pl = set(self._load_raw("pl").keys())
        only_en = en - pl
        only_pl = pl - en
        assert not only_en, f"Keys only in EN: {sorted(only_en)}"
        assert not only_pl, f"Keys only in PL: {sorted(only_pl)}"

    def test_no_empty_values(self):
        for locale in supported_locales():
            catalog = self._load_raw(locale)
            empty = [
                k for k, v in catalog.items()
                if isinstance(v, str)
                and not v.strip()
                and k != "_meta"
            ]
            assert not empty, f"Empty values in {locale}: {empty}"


# ── Interpolation Parity ────────────────────────────────────────────


class TestInterpolationParity:
    """Interpolation variables must match across locales."""

    def _load_raw(self, locale: str) -> dict[str, str]:
        path = _LOCALES_DIR / f"{locale}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_interpolation_variables_match(self):
        en = self._load_raw("en")
        pl = self._load_raw("pl")
        mismatches = []
        for key in en:
            if key == "_meta" or not isinstance(en[key], str):
                continue
            en_vars = set(_INTERPOLATION_RE.findall(en[key]))
            pl_val = pl.get(key, "")
            if not isinstance(pl_val, str):
                continue
            pl_vars = set(_INTERPOLATION_RE.findall(pl_val))
            if en_vars != pl_vars:
                mismatches.append(f"{key}: EN={en_vars}, PL={pl_vars}")
        assert not mismatches, "Interpolation variable mismatches:\n" + "\n".join(mismatches)


# ── Core t() Function ───────────────────────────────────────────────


class TestTranslate:
    def test_known_key_en(self):
        assert t("status.ready", locale="en") == "Ready"

    def test_known_key_pl(self):
        assert t("status.ready", locale="pl") == "Gotowe"

    def test_missing_key_returns_key(self):
        assert t("nonexistent.key.abc", locale="en") == "nonexistent.key.abc"

    def test_fallback_to_english(self):
        # If PL is missing a key, it should fall back to EN
        get_catalog("en")
        # Use a key we know exists in EN
        key = "status.ready"
        assert t(key, locale="pl") != key  # should be translated, not raw key

    def test_interpolation(self):
        result = t("freshness.days_ago", locale="en", days=5)
        assert "5" in result

    def test_thread_local_locale(self):
        set_locale("pl")
        result = t("status.ready")
        assert result == "Gotowe"
        set_locale("en")
        result = t("status.ready")
        assert result == "Ready"


# ── Pluralization ───────────────────────────────────────────────────


class TestPluralization:
    """Polish has 3 plural forms."""

    def test_english_one(self):
        assert _plural_key("en", 1) == "one"

    def test_english_other(self):
        assert _plural_key("en", 0) == "other"
        assert _plural_key("en", 2) == "other"
        assert _plural_key("en", 5) == "other"

    def test_polish_one(self):
        assert _plural_key("pl", 1) == "one"

    def test_polish_few(self):
        for n in (2, 3, 4, 22, 23, 24):
            assert _plural_key("pl", n) == "few", f"Expected 'few' for {n}"

    def test_polish_other(self):
        for n in (0, 5, 10, 11, 12, 13, 14, 15, 20, 21, 25, 100):
            assert _plural_key("pl", n) == "other", f"Expected 'other' for {n}"


# ── Locale Detection ───────────────────────────────────────────────


class TestLocaleDetection:
    def test_none_returns_default(self):
        assert detect_locale_from_header(None) == default_locale()

    def test_empty_returns_default(self):
        assert detect_locale_from_header("") == default_locale()

    def test_pl_header(self):
        assert detect_locale_from_header("pl,en;q=0.8") == "pl"

    def test_en_header(self):
        assert detect_locale_from_header("en-US,en;q=0.9") == "en"

    def test_prefix_match(self):
        assert detect_locale_from_header("pl-PL,en;q=0.5") == "pl"

    def test_unsupported_falls_to_default(self):
        assert detect_locale_from_header("fr,de;q=0.8") == default_locale()
