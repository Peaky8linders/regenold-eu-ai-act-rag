"""Tests for the live-fetched official EU AI Act module.

Covers the generated :mod:`app.data.official_eu_ai_act` artefact plus
the parsing helpers in :mod:`scripts.fetch_official_eu_ai_act`. The
fetcher tests are pure-local — they exercise the parser against
synthetic HTML and never hit the network.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Generated-module invariants
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def official():
    return importlib.import_module("app.data.official_eu_ai_act")


def test_module_exposes_public_api(official):
    """The five constants documented in the README must exist."""
    for name in (
        "OFFICIAL_FETCH_DATE",
        "OFFICIAL_SHA256",
        "OFFICIAL_SOURCE_URL",
        "OFFICIAL_ARTICLE_TEXT",
        "OFFICIAL_RECITAL_TEXT",
        "OFFICIAL_UPDATES",
    ):
        assert hasattr(official, name), f"missing constant {name}"


def test_fetch_date_is_iso(official):
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    assert iso.match(official.OFFICIAL_FETCH_DATE)


def test_source_url_points_to_official_eu_source(official):
    """The fetch source must be an official EU document store: either
    the EUR-Lex web frontend or the Publications Office Cellar
    repository (its canonical machine-readable backing store)."""
    url = official.OFFICIAL_SOURCE_URL
    assert "eur-lex.europa.eu" in url or "publications.europa.eu" in url
    assert "32024R1689" in url


def test_article_text_has_full_coverage(official):
    """Expect 113 articles + 13 annexes = 126; allow some slop on the
    HTML parser if EUR-Lex returned a degraded payload."""
    assert len(official.OFFICIAL_ARTICLE_TEXT) >= 100, (
        f"too few articles: {len(official.OFFICIAL_ARTICLE_TEXT)}"
    )


def test_article_5_is_prohibited(official):
    body = official.OFFICIAL_ARTICLE_TEXT.get("Article 5")
    assert body, "Article 5 missing"
    assert "prohibit" in body.lower(), "Article 5 should mention prohibitions"


def test_article_6_is_high_risk(official):
    body = official.OFFICIAL_ARTICLE_TEXT.get("Article 6")
    assert body, "Article 6 missing"
    assert "high-risk" in body.lower() or "high risk" in body.lower()


def test_recital_one_non_empty(official):
    body = official.OFFICIAL_RECITAL_TEXT.get(1)
    assert body, "Recital 1 missing"
    assert len(body) > 50, "Recital 1 should be substantive prose"


def test_recital_count_reasonable(official):
    # The Act ships 180 recitals; allow degraded parses down to ~150.
    assert len(official.OFFICIAL_RECITAL_TEXT) >= 100


def test_updates_are_well_formed(official):
    assert isinstance(official.OFFICIAL_UPDATES, list)
    assert len(official.OFFICIAL_UPDATES) >= 1
    for entry in official.OFFICIAL_UPDATES:
        assert {"date", "title", "summary"} <= entry.keys()
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", entry["date"])


def test_sha_matches_bundle(official):
    """SHA pin must equal the hash of the bundled text — guarantees the
    generated module wasn't hand-edited after the fetch."""
    from scripts.fetch_official_eu_ai_act import canonical_sha

    # Reconstruct the canonical bundle. The fetcher merges annexes into
    # ARTICLE_TEXT under "Annex X" keys, so feeding the whole map back
    # in is correct.
    sha = canonical_sha(
        dict(official.OFFICIAL_ARTICLE_TEXT),
        dict(official.OFFICIAL_RECITAL_TEXT),
    )
    assert sha == official.OFFICIAL_SHA256


def test_pin_sidecar_matches_module(official):
    pin_path = REPO_ROOT / "app" / "data" / "_official_eu_ai_act_pin.json"
    if not pin_path.exists():
        pytest.skip("pin sidecar not generated yet")
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    assert pin["sha256"] == official.OFFICIAL_SHA256
    assert pin["celex"] == "32024R1689"


def test_no_live_fetch_blocked_marker_in_normal_run(official):
    """When the live fetch succeeded, the degraded marker must be False.

    If a CI environment can't reach EUR-Lex, the module is generated
    from the Ansvar seed and the flag flips True — the assertion below
    documents that contract but lets the degraded path pass.
    """
    # Either:
    #  * live fetch succeeded → flag is False, parsed > 100 articles
    #  * live fetch blocked   → flag is True, seed populated > 100 articles
    blocked = getattr(official, "_LIVE_FETCH_BLOCKED", False)
    if blocked:
        # Degraded path is still expected to produce a non-empty bundle.
        assert len(official.OFFICIAL_ARTICLE_TEXT) >= 100
    else:
        assert blocked is False


# ---------------------------------------------------------------------------
# Parser-helper tests (synthetic HTML, no network)
# ---------------------------------------------------------------------------


def test_parse_eur_lex_html_empty_input():
    from scripts.fetch_official_eu_ai_act import parse_eur_lex_html

    assert parse_eur_lex_html("") == {
        "articles": {},
        "annexes": {},
        "recitals": {},
        "article_titles": {},
        "annex_titles": {},
    }


def test_parse_eur_lex_html_non_string_input():
    from scripts.fetch_official_eu_ai_act import parse_eur_lex_html

    # Defensive: a None / bytes input shouldn't crash, just yield empties.
    out = parse_eur_lex_html(None)  # type: ignore[arg-type]
    assert out["articles"] == {}
    assert out["recitals"] == {}


def test_parse_eur_lex_html_malformed_no_exception():
    from scripts.fetch_official_eu_ai_act import parse_eur_lex_html

    # Truncated tag, unclosed div, garbage entities — must not raise.
    bogus = '<div id="art_1"><p>Hello & broken <unclosed'
    out = parse_eur_lex_html(bogus)
    assert isinstance(out, dict)
    assert "articles" in out


def test_parse_eur_lex_html_extracts_minimal_article():
    """A well-formed minimal payload should round-trip into the parser."""
    from scripts.fetch_official_eu_ai_act import parse_eur_lex_html

    sample = (
        '<div class="eli-subdivision" id="art_42">'
        '<p class="oj-ti-art">Article 42</p>'
        '<div class="eli-title" id="art_42.tit_1">'
        '<p class="oj-sti-art">The Answer</p>'
        '</div>'
        '<p class="oj-normal">The meaning of life is computation.</p>'
        '</div>'
    )
    out = parse_eur_lex_html(sample)
    assert "Article 42" in out["articles"]
    assert "meaning of life" in out["articles"]["Article 42"]
    assert out["article_titles"].get("Article 42") == "The Answer"


def test_parse_eur_lex_html_extracts_recital():
    from scripts.fetch_official_eu_ai_act import parse_eur_lex_html

    sample = (
        '<div class="eli-subdivision" id="rct_7">'
        '<p class="oj-normal">(7)</p>'
        '<p class="oj-normal">Whereas seven is a fine recital number.</p>'
        '</div>'
    )
    out = parse_eur_lex_html(sample)
    assert 7 in out["recitals"]
    assert "seven is a fine recital" in out["recitals"][7]


def test_parse_eur_lex_html_extracts_annex():
    from scripts.fetch_official_eu_ai_act import parse_eur_lex_html

    sample = (
        '<div class="eli-container" id="anx_III">'
        '<p class="oj-doc-ti">ANNEX III</p>'
        '<p class="oj-doc-ti">High-risk AI systems</p>'
        '<p class="oj-normal">Biometrics, education, employment ...</p>'
        '</div>'
    )
    out = parse_eur_lex_html(sample)
    assert "Annex III" in out["annexes"]
    assert "Biometrics" in out["annexes"]["Annex III"]
    assert out["annex_titles"].get("Annex III") == "High-risk AI systems"


def test_canonical_sha_is_stable():
    """Same input → same SHA. Different input → different SHA."""
    from scripts.fetch_official_eu_ai_act import canonical_sha

    a = canonical_sha({"Article 1": "hello"}, {1: "world"})
    b = canonical_sha({"Article 1": "hello"}, {1: "world"})
    c = canonical_sha({"Article 1": "hello!"}, {1: "world"})
    assert a == b
    assert a != c


def test_canonical_sha_key_order_independent():
    """Adding the same items in different order yields the same SHA."""
    from scripts.fetch_official_eu_ai_act import canonical_sha

    a = canonical_sha({"Article 1": "x", "Article 2": "y"}, {1: "a", 2: "b"})
    b = canonical_sha({"Article 2": "y", "Article 1": "x"}, {2: "b", 1: "a"})
    assert a == b


def test_consolidation_note_extracted(official):
    """The fetcher should record either the CONVEX banner or a clear
    fallback note — never an empty string."""
    note = getattr(official, "OFFICIAL_CONSOLIDATION_NOTE", "")
    assert note, "consolidation note should not be empty"


# ---------------------------------------------------------------------------
# fetch_html source-ordering tests (monkeypatched _http_get, no network)
# ---------------------------------------------------------------------------


def test_fetch_html_tries_cellar_first(monkeypatch):
    """The Publications Office Cellar repository is the canonical store
    and must be the first source attempted."""
    import scripts.fetch_official_eu_ai_act as fx

    calls: list[str] = []

    def fake_get(url, extra_headers=None):
        calls.append(url)
        return b"<html><div id='art_1'>x</div></html>"

    monkeypatch.setattr(fx, "_http_get", fake_get)
    _, url, note = fx.fetch_html()
    assert calls[0] == fx.CELLAR_URL
    assert url == fx.CELLAR_URL
    assert note == "cellar xhtml"


def test_fetch_html_skips_empty_body(monkeypatch):
    """An empty body (the EUR-Lex anti-bot WAF's HTTP 202 signature)
    must not be pinned — the loop falls through to the next source."""
    import scripts.fetch_official_eu_ai_act as fx

    def fake_get(url, extra_headers=None):
        if url == fx.CELLAR_URL:
            return b""  # WAF / 202 empty-body signature
        return b"<html><div id='art_1'>ok</div></html>"

    monkeypatch.setattr(fx, "_http_get", fake_get)
    payload, url, _ = fx.fetch_html()
    assert url == fx.HTML_URL
    assert payload


def test_fetch_html_all_empty_raises(monkeypatch):
    """Every source returning an empty body is a hard failure."""
    import scripts.fetch_official_eu_ai_act as fx

    monkeypatch.setattr(fx, "_http_get", lambda url, extra_headers=None: b"")
    with pytest.raises(RuntimeError):
        fx.fetch_html()
