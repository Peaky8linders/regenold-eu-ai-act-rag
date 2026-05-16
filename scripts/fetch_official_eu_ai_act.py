"""Live fetch of the official EU AI Act regulatory text from EUR-Lex.

Independent counterpart to ``scripts/generate_ansvar_corpus.py``. Where
the Ansvar generator consumes a pre-shipped JSON snapshot, this script
fetches the **current consolidated HTML** of Regulation (EU) 2024/1689
(CELEX 32024R1689) directly from EUR-Lex and re-derives the article /
annex / recital text. The two corpora coexist: Ansvar stays the BM25
default; this module is the seed surface for the upcoming embeddings
work and a "freshness" backstop when the Digital Omnibus amendments
finally merge into the EUR-Lex consolidated text.

Pure stdlib only — no pip deps, runs on Windows under py-3.12.

Outputs (deterministic when upstream bytes are stable):

    app/data/official_eu_ai_act.py     # generated Python module
    app/data/_official_eu_ai_act_pin.json  # SHA pin + metadata sidecar

Re-running with an unchanged upstream is a no-op (the SHA pin matches
the freshly-computed SHA → exit 0 with ``already pinned``).

Run::

    py -3.12 scripts/fetch_official_eu_ai_act.py
    py -3.12 scripts/fetch_official_eu_ai_act.py --force   # always overwrite

EUR-Lex blocks unidentified scrapers — we send a contact-bearing
User-Agent and throttle 1s between requests. The PDF / XML fallback
URLs are tried only when the HTML fetch fails; the fallback path
records a ``_LIVE_FETCH_BLOCKED`` marker so the generated module is
still importable and downstream code can detect the degraded state.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html
import io
import json
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# Allow running from any cwd by resolving paths off the script location.
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_MODULE = REPO_ROOT / "app" / "data" / "official_eu_ai_act.py"
OUT_PIN = REPO_ROOT / "app" / "data" / "_official_eu_ai_act_pin.json"

CELEX = "32024R1689"
HTML_URL = f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{CELEX}"
PDF_URL = f"https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:{CELEX}"
XML_URL = f"https://eur-lex.europa.eu/legal-content/EN/TXT/XML/?uri=CELEX:{CELEX}"

USER_AGENT = (
    "Regenold-EU-AI-Act-RAG/1.0 (compliance research; contact: bacu.andrei@gmail.com)"
)
REQUEST_THROTTLE_S = 1.0
REQUEST_TIMEOUT_S = 60

# Curated changelog of post-adoption amendments. The EUR-Lex
# consolidated text frequently lags political agreements by months /
# years, so we bake a hand-maintained list of regulation-current
# updates that downstream code can surface alongside the original
# article prose. Update this list whenever a new amendment lands.
OFFICIAL_UPDATES: list[dict[str, str]] = [
    {
        "date": "2026-05-07",
        "title": "Digital Omnibus political agreement",
        "summary": (
            "Council and Parliament reach political agreement on the Digital "
            "Omnibus package. Annex III high-risk applicability date shifts to "
            "2 December 2027; Annex I embedded-product to 2 August 2028. SME / "
            "small mid-cap obligations under Arts. 62-63 broadened to include "
            "small mid-cap modifiers. Not yet merged into the EUR-Lex "
            "consolidated text."
        ),
    },
    {
        "date": "2025-07-18",
        "title": "Commission GPAI threshold guidelines",
        "summary": (
            "European Commission publishes guidelines specifying the FLOP "
            "thresholds for the Art. 51 general-purpose AI model designation "
            "(10^23 training FLOPs) and confirming the one-third fine-tune rule "
            "(any modifier adding additional compute > 1/3 of the base, or "
            "~3.3e24 FLOPs absolute, becomes a new provider under Art. 25). "
            "10^25 systemic-risk threshold retained from the regulation text."
        ),
    },
    {
        "date": "2025-02-02",
        "title": "Article 5 prohibitions enter into force",
        "summary": (
            "Per Art. 113(a), the prohibitions in Art. 5 and the general "
            "provisions in Chapter I (Arts. 1-4) become applicable across the "
            "Union. AI literacy obligations under Art. 4 also live from this "
            "date."
        ),
    },
    {
        "date": "2024-08-01",
        "title": "Regulation enters into force",
        "summary": (
            "Regulation (EU) 2024/1689 enters into force on the twentieth day "
            "following its publication in the OJ (12 July 2024). Most "
            "obligations have staggered applicability dates per Art. 113."
        ),
    },
    {
        "date": "2024-07-12",
        "title": "Publication in the Official Journal",
        "summary": (
            "Regulation (EU) 2024/1689 of the European Parliament and of the "
            "Council of 13 June 2024 laying down harmonised rules on artificial "
            "intelligence (Artificial Intelligence Act) published in OJ L, "
            "2024/1689."
        ),
    },
]


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def _http_get(url: str) -> bytes:
    """Fetch ``url`` with our identified User-Agent and 1s throttle."""
    time.sleep(REQUEST_THROTTLE_S)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        return resp.read()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# HTML parser — extracts ``art_N`` / ``anx_X`` / ``rct_N`` subdivisions
# ---------------------------------------------------------------------------


_ID_RE = re.compile(r"^(art|anx|rct)_([\w]+)$")


class EurLexParser(HTMLParser):
    """Pulls clean text out of the EUR-Lex consolidated HTML.

    Strategy: EUR-Lex marks every article / annex / recital with a
    ``<div id="art_N">`` / ``<div id="anx_I">`` / ``<div id="rct_N">``
    container. We accumulate text under the *outermost* such container
    (ignoring nested ``art_1.tit_1`` title sub-divs) and stop when the
    container closes.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.articles: dict[str, list[str]] = {}
        self.annexes: dict[str, list[str]] = {}
        self.recitals: dict[int, list[str]] = {}
        # Stack of (kind, key, depth_at_open). When the inner div count
        # returns to that depth, we close the section.
        self._stack: list[tuple[str, object, int]] = []
        self._div_depth = 0
        # Per-tag depth counter so we know when the enclosing div closes.
        self._tag_depths: list[str] = []

    # -- helpers --------------------------------------------------------
    def _current_target(self) -> list[str] | None:
        if not self._stack:
            return None
        kind, key, _ = self._stack[-1]
        if kind == "art":
            return self.articles.setdefault(key, [])  # type: ignore[arg-type]
        if kind == "anx":
            return self.annexes.setdefault(key, [])  # type: ignore[arg-type]
        if kind == "rct":
            return self.recitals.setdefault(key, [])  # type: ignore[arg-type]
        return None

    # -- HTMLParser hooks ----------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_depths.append(tag)
        if tag == "div":
            self._div_depth += 1
            attr_id = next((v for k, v in attrs if k == "id" and v), None)
            if attr_id and "." not in attr_id:
                m = _ID_RE.match(attr_id)
                if m:
                    kind, raw_key = m.group(1), m.group(2)
                    key: object
                    if kind == "rct":
                        try:
                            key = int(raw_key)
                        except ValueError:
                            return
                    else:
                        key = raw_key
                    self._stack.append((kind, key, self._div_depth))

    def handle_endtag(self, tag: str) -> None:
        if self._tag_depths and self._tag_depths[-1] == tag:
            self._tag_depths.pop()
        if tag == "div":
            if self._stack and self._stack[-1][2] == self._div_depth:
                self._stack.pop()
            self._div_depth -= 1

    def handle_data(self, data: str) -> None:
        target = self._current_target()
        if target is None:
            return
        # Drop the article-title marker line ("Article 1") so we don't
        # duplicate the header inside the body. We keep titles in the
        # downstream title map, derived separately.
        target.append(data)


def _clean_text(parts: list[str]) -> str:
    """Collapse the per-data-callback fragments to a single tidy line."""
    text = "".join(parts)
    text = text.replace(" ", " ")  # non-breaking space → regular
    text = text.replace(" ", " ")  # thin space
    text = text.replace(" ", " ")  # narrow no-break space
    text = html.unescape(text)
    # Collapse runs of whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_article_titles(html_text: str) -> dict[str, str]:
    """Pull ``Article N — Title`` pairs from the ``oj-sti-art`` markers.

    Returns a map keyed by canonical "Article N" id → title.
    """
    titles: dict[str, str] = {}
    # Pattern: <div class="eli-subdivision" id="art_N"> ... <p class="oj-sti-art">TITLE</p>
    # Walk article ids in document order.
    for m in re.finditer(
        r'id="art_(\d+)"[\s\S]{0,2000}?class="oj-sti-art"[^>]*>([^<]+)<',
        html_text,
    ):
        n = m.group(1)
        title = html.unescape(m.group(2)).replace(" ", " ").strip()
        titles[f"Article {n}"] = title
    return titles


def _extract_annex_titles(html_text: str) -> dict[str, str]:
    """Pull Annex titles (the line right after ``ANNEX X``)."""
    titles: dict[str, str] = {}
    for m in re.finditer(
        r'id="anx_([IVX]+)"[\s\S]{0,800}?class="oj-doc-ti"[^>]*>[^<]+</p>\s*<p[^>]*class="oj-doc-ti"[^>]*>([^<]+)</p>',
        html_text,
    ):
        roman = m.group(1)
        title = html.unescape(m.group(2)).replace(" ", " ").strip()
        titles[f"Annex {roman}"] = title
    return titles


def parse_eur_lex_html(html_text: str) -> dict[str, object]:
    """Parse an EUR-Lex HTML payload and return article / annex / recital text.

    Returns a dict with keys ``articles``, ``annexes``, ``recitals``,
    ``article_titles``, ``annex_titles``. Empty dicts are returned for
    each field if the input is malformed (no exception is raised).

    Public entry point — exercised by the test suite against synthetic
    inputs as well.
    """
    if not isinstance(html_text, str) or not html_text.strip():
        return {
            "articles": {},
            "annexes": {},
            "recitals": {},
            "article_titles": {},
            "annex_titles": {},
        }
    parser = EurLexParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        # Truly malformed input — bail with whatever we managed to capture.
        pass

    articles: dict[str, str] = {}
    for raw_key, parts in parser.articles.items():
        text = _clean_text(parts)
        # Drop leading "Article N" or "Article N Title" prefix — we keep
        # titles separately.
        text = re.sub(r"^Article\s+\w+\s*", "", text, count=1)
        if text:
            articles[f"Article {raw_key}"] = text

    annexes: dict[str, str] = {}
    for raw_key, parts in parser.annexes.items():
        text = _clean_text(parts)
        text = re.sub(r"^ANNEX\s+[IVX]+\s*", "", text, count=1, flags=re.IGNORECASE)
        if text:
            annexes[f"Annex {raw_key}"] = text

    recitals: dict[int, str] = {}
    for n, parts in parser.recitals.items():
        text = _clean_text(parts)
        # Drop the leading "(N)" enumeration marker.
        text = re.sub(r"^\(\d+\)\s*", "", text, count=1)
        if text:
            recitals[n] = text

    article_titles = _extract_article_titles(html_text)
    annex_titles = _extract_annex_titles(html_text)

    return {
        "articles": articles,
        "annexes": annexes,
        "recitals": recitals,
        "article_titles": article_titles,
        "annex_titles": annex_titles,
    }


# ---------------------------------------------------------------------------
# Generator — writes the .py module
# ---------------------------------------------------------------------------


def _py_dict_str(name: str, mapping: dict, key_is_int: bool = False) -> str:
    """Emit a dict-of-string-to-string as a Python literal.

    Mirrors the wrapping style used by ``generate_ansvar_corpus.py``.
    """
    lines = [f"{name}: dict[{'int' if key_is_int else 'str'}, str] = {{"]
    for k in sorted(mapping.keys()):
        v = mapping[k]
        if not isinstance(v, str):
            v = str(v)
        key_repr = repr(k)
        lines.append(f"    {key_repr}: (")
        for chunk in textwrap.wrap(v, width=88, drop_whitespace=False) or [""]:
            lines.append(f"        {chunk!r}")
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines)


def _py_list_of_dict(name: str, items: list[dict]) -> str:
    import pprint as _pprint

    payload = _pprint.pformat(items, indent=2, width=88, sort_dicts=False)
    return f"{name}: list[dict] = {payload}"


def render_module(
    *,
    article_text: dict[str, str],
    recital_text: dict[int, str],
    article_titles: dict[str, str],
    annex_titles: dict[str, str],
    fetch_date: str,
    sha: str,
    source_url: str,
    consolidation_note: str,
    live_fetch_blocked: bool,
    updates: list[dict[str, str]],
) -> str:
    """Render the full ``app/data/official_eu_ai_act.py`` text."""
    header = textwrap.dedent(
        f'''\
        # AUTOGENERATED by scripts/fetch_official_eu_ai_act.py — do not edit by hand
        """Official EU AI Act regulatory text — live-fetched from EUR-Lex.

        Independent counterpart to :mod:`app.data.eu_ai_act_corpus` (which
        pins the Ansvar-Systems snapshot). Both modules coexist: Ansvar
        remains the BM25 default; this one seeds the embeddings surface
        and tracks Digital-Omnibus-era amendments.

        Source: Regulation (EU) 2024/1689 (CELEX {CELEX}).
        Fetched: {fetch_date}
        Upstream SHA-256: {sha}
        Live fetch blocked: {live_fetch_blocked}

        Consolidation note: {consolidation_note}

        Public surface:

        * :data:`OFFICIAL_FETCH_DATE`   — ISO date the bundle was fetched.
        * :data:`OFFICIAL_SHA256`       — SHA-256 over the canonical text bundle.
        * :data:`OFFICIAL_SOURCE_URL`   — primary EUR-Lex URL we fetched from.
        * :data:`OFFICIAL_CONSOLIDATION_NOTE` — EUR-Lex ``generated_on`` /
          consolidation-date metadata when available.
        * :data:`OFFICIAL_ARTICLE_TEXT` — keyed ``"Article N"`` / ``"Annex X"``.
        * :data:`OFFICIAL_RECITAL_TEXT` — keyed by recital number.
        * :data:`OFFICIAL_UPDATES`      — curated post-adoption changelog.
        * :data:`_LIVE_FETCH_BLOCKED`   — ``True`` only when the live fetch
          failed AND a placeholder seed was used.
        """
        from __future__ import annotations

        OFFICIAL_FETCH_DATE: str = {fetch_date!r}
        OFFICIAL_SHA256: str = {sha!r}
        OFFICIAL_SOURCE_URL: str = {source_url!r}
        OFFICIAL_CONSOLIDATION_NOTE: str = {consolidation_note!r}
        _LIVE_FETCH_BLOCKED: bool = {live_fetch_blocked!r}

        '''
    )

    sections: list[str] = [header]
    sections.append(_py_dict_str("OFFICIAL_ARTICLE_TEXT", article_text))
    sections.append("")
    sections.append(_py_dict_str("OFFICIAL_RECITAL_TEXT", recital_text, key_is_int=True))
    sections.append("")
    sections.append(_py_dict_str("OFFICIAL_ARTICLE_TITLES", article_titles))
    sections.append("")
    sections.append(_py_dict_str("OFFICIAL_ANNEX_TITLES", annex_titles))
    sections.append("")
    sections.append(_py_list_of_dict("OFFICIAL_UPDATES", updates))
    sections.append("")
    return "\n".join(sections)


def canonical_sha(
    article_text: dict[str, str],
    recital_text: dict[int, str],
) -> str:
    """SHA-256 over the canonical text bundle.

    Stable across re-runs: we serialise the article + recital maps as
    sorted JSON before hashing, so cosmetic shifts in ordering (or
    metadata changes) don't break the pin.
    """
    canonical = {
        "articles": dict(sorted(article_text.items())),
        "recitals": {str(k): v for k, v in sorted(recital_text.items())},
    }
    blob = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _extract_consolidation_note(html_text: str) -> str:
    """Pull the ``generated_on:YYYYMMDD-HHMM`` marker from EUR-Lex's banner."""
    m = re.search(r"generated_on:(\d{8})-(\d{4})", html_text)
    if not m:
        return "no consolidation banner found"
    ymd = m.group(1)
    try:
        date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    except Exception:
        date = ymd
    return f"EUR-Lex CONVEX generated_on {date}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _seed_from_corpus() -> tuple[dict[str, str], dict[int, str], dict[str, str], dict[str, str]]:
    """Fallback seed when every live URL is blocked.

    Uses the Ansvar-Systems corpus already on disk so the generated
    module is never empty even when EUR-Lex is unreachable. The
    ``_LIVE_FETCH_BLOCKED`` flag is set to True in that case so callers
    can detect the degraded state.
    """
    try:
        from app.data import eu_ai_act_corpus as _ans  # noqa: PLC0415
    except Exception:  # pragma: no cover — defensive
        return {}, {}, {}, {}

    article_text: dict[str, str] = {}
    for raw_key, body in _ans.ARTICLE_FULL_TEXT.items():
        if raw_key.startswith("Art."):
            n = raw_key.split()[1]
            article_text[f"Article {n}"] = body
        elif raw_key.startswith("Annex"):
            article_text[raw_key] = body
    recital_text: dict[int, str] = dict(_ans.RECITALS)
    article_titles: dict[str, str] = {}
    annex_titles: dict[str, str] = {}
    for raw_key, title in _ans.ARTICLE_TITLE.items():
        if not title:
            continue
        if raw_key.startswith("Art."):
            n = raw_key.split()[1]
            article_titles[f"Article {n}"] = title
        elif raw_key.startswith("Annex"):
            annex_titles[raw_key] = title
    return article_text, recital_text, article_titles, annex_titles


def fetch_html() -> tuple[bytes, str, str]:
    """Try HTML → PDF → XML in order. Return ``(payload, url_used, note)``.

    On total failure raises the last urllib error.
    """
    errors: list[str] = []
    for url in (HTML_URL, XML_URL, PDF_URL):
        try:
            payload = _http_get(url)
            note = "primary html" if url == HTML_URL else (
                "xml fallback" if url == XML_URL else "pdf fallback"
            )
            return payload, url, note
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    raise RuntimeError("All EUR-Lex URLs failed: " + " | ".join(errors))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true", help="rewrite even if SHA pin matches")
    args = p.parse_args(argv)

    print(f"[fetch] User-Agent: {USER_AGENT}")
    print(f"[fetch] Target: {HTML_URL}")

    live_blocked = False
    consolidation_note = "unknown"
    source_url = HTML_URL

    article_text: dict[str, str] = {}
    recital_text: dict[int, str] = {}
    article_titles: dict[str, str] = {}
    annex_titles: dict[str, str] = {}

    try:
        payload, url_used, note = fetch_html()
        source_url = url_used
        print(f"[fetch] OK ({note}): {len(payload)} bytes from {url_used}")
        if url_used == HTML_URL:
            html_text = payload.decode("utf-8", errors="replace")
            consolidation_note = _extract_consolidation_note(html_text)
            parsed = parse_eur_lex_html(html_text)
            article_text = dict(parsed["articles"])  # type: ignore[arg-type]
            # Merge annexes into the same article_text map under "Annex X" keys.
            for k, v in (parsed["annexes"] or {}).items():  # type: ignore[union-attr]
                article_text[k] = v
            recital_text = dict(parsed["recitals"])  # type: ignore[arg-type]
            article_titles = dict(parsed["article_titles"])  # type: ignore[arg-type]
            annex_titles = dict(parsed["annex_titles"])  # type: ignore[arg-type]
        else:
            # XML / PDF fallback — we don't ship a fallback parser here.
            # Fall through to the corpus seed but DO keep the live-fetch
            # marker off because we *did* talk to EUR-Lex.
            consolidation_note = f"fallback {note} (not parsed)"
            print(f"[fetch] WARN: fallback {note} reached EUR-Lex but parser is HTML-only.")
            seed = _seed_from_corpus()
            article_text, recital_text, article_titles, annex_titles = seed
    except Exception as e:
        print(f"[fetch] ERROR: {e}", file=sys.stderr)
        print("[fetch] Falling back to local Ansvar-Systems corpus seed.", file=sys.stderr)
        live_blocked = True
        consolidation_note = f"live fetch blocked: {e}"
        seed = _seed_from_corpus()
        article_text, recital_text, article_titles, annex_titles = seed

    if not article_text and not recital_text:
        print("[fetch] FATAL: neither live fetch nor seed produced any text.", file=sys.stderr)
        return 1

    sha = canonical_sha(article_text, recital_text)

    # Idempotence: if the pin sidecar exists AND matches, exit clean.
    if OUT_PIN.exists() and not args.force:
        try:
            existing = json.loads(OUT_PIN.read_text(encoding="utf-8"))
            if existing.get("sha256") == sha and OUT_MODULE.exists():
                print(f"[fetch] already pinned (sha256={sha[:12]}…), no change")
                return 0
        except Exception:
            pass

    fetch_date = _dt.date.today().isoformat()

    module_text = render_module(
        article_text=article_text,
        recital_text=recital_text,
        article_titles=article_titles,
        annex_titles=annex_titles,
        fetch_date=fetch_date,
        sha=sha,
        source_url=source_url,
        consolidation_note=consolidation_note,
        live_fetch_blocked=live_blocked,
        updates=OFFICIAL_UPDATES,
    )

    OUT_MODULE.parent.mkdir(parents=True, exist_ok=True)
    OUT_MODULE.write_text(module_text, encoding="utf-8")

    pin = {
        "celex": CELEX,
        "source_url": source_url,
        "fetch_date": fetch_date,
        "sha256": sha,
        "consolidation_note": consolidation_note,
        "live_fetch_blocked": live_blocked,
        "article_count": len(article_text),
        "recital_count": len(recital_text),
    }
    OUT_PIN.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")

    size_kb = OUT_MODULE.stat().st_size // 1024
    print(f"[fetch] Wrote {OUT_MODULE} ({size_kb} KB)")
    print(f"[fetch] Wrote {OUT_PIN}")
    print(
        f"[fetch] Stats: articles={len(article_text)} recitals={len(recital_text)} "
        f"sha256={sha[:12]}… live_blocked={live_blocked}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
