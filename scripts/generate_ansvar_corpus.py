"""Generate `app/data/eu_ai_act_corpus.py` from the upstream Ansvar JSON.

Reads `evals/bench/data/upstream/ansvar_ai_act_full.json` (EUR-Lex
consolidated text shipped by https://github.com/Ansvar-Systems/EU_compliance_MCP
under Apache 2.0; the regulation text itself is public-domain per
Article 297 TFEU) plus `ansvar_ai_act_guide.json` (curated
proportionality / pitfalls layer) and `ansvar_ai_act_applicability.json`
(sector → article rules).

Emits a single Python module with:

    ARTICLE_FULL_TEXT  : dict[str, str]   # keyed "Art. 1" / "Annex IV"
    ARTICLE_TITLE      : dict[str, str]
    ARTICLE_CHAPTER    : dict[str, str | None]
    ART_3_DEFINITIONS  : dict[str, str]   # 68 Art. 3 terms
    RECITALS           : dict[int, str]
    PITFALLS           : list[dict]
    PROPORTIONALITY    : list[dict]       # 7-tier risk pyramid
    APPLICABILITY_RULES: list[dict]

The output is deterministic — re-running the generator on the same
input bytes produces a byte-identical module. Run only when refreshing
the corpus snapshot (the SHA in the module header pins which upstream
commit it was derived from).

Run:
    py -3.12 scripts/generate_ansvar_corpus.py

The generator is data-only; no engine wiring lives here. See
``app/data/eu_ai_act_corpus.py`` for the generated artefact and
``app/engines/graph_rag.py`` / ``app/data/kb.py`` for the consumers.
"""
from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path

UPSTREAM_DIR = Path("evals/bench/data/upstream")
FULL_JSON = UPSTREAM_DIR / "ansvar_ai_act_full.json"
GUIDE_JSON = UPSTREAM_DIR / "ansvar_ai_act_guide.json"
APPLIC_JSON = UPSTREAM_DIR / "ansvar_ai_act_applicability.json"
OUT_PATH = Path("app/data/eu_ai_act_corpus.py")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalise_number(raw: str | int) -> str | None:
    """Convert upstream `number` (int or "Annex I" string) to our key form.

    * Integer 1 → ``"Art. 1"``.
    * String ``"Annex I"`` → ``"Annex I"`` (uppercase Roman, no change).
    * Anything else → ``None`` (skip).
    """
    if isinstance(raw, int):
        return f"Art. {raw}"
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("Annex"):
            return s
        if s.isdigit():
            return f"Art. {int(s)}"
    return None


def _py_repr(s: str) -> str:
    """Triple-quote a string safely for inclusion in the generated module.

    Strips trailing whitespace per line, escapes triple-quote sequences.
    """
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if '"""' in s:
        s = s.replace('"""', '\\"\\"\\"')
    return f'"""{s}"""'


def main() -> int:
    full = json.loads(FULL_JSON.read_text(encoding="utf-8"))
    guide = json.loads(GUIDE_JSON.read_text(encoding="utf-8"))
    applic = json.loads(APPLIC_JSON.read_text(encoding="utf-8"))

    article_text: dict[str, str] = {}
    article_title: dict[str, str] = {}
    article_chapter: dict[str, str | None] = {}

    for art in full.get("articles", []):
        key = _normalise_number(art.get("number"))
        if not key:
            continue
        text = (art.get("text") or "").strip()
        if not text:
            continue
        article_text[key] = text
        article_title[key] = (art.get("title") or "").strip()
        article_chapter[key] = art.get("chapter")

    definitions: dict[str, str] = {}
    for d in full.get("definitions", []):
        term = (d.get("term") or "").strip()
        body = (d.get("definition") or "").strip()
        if term and body:
            definitions[term] = body

    recitals: dict[int, str] = {}
    for r in full.get("recitals", []):
        # Upstream shape: {"recital_number": int, "text": str}.
        num = r.get("recital_number") if "recital_number" in r else r.get("number")
        try:
            num = int(num)
        except (TypeError, ValueError):
            continue
        body = (r.get("text") or "").strip()
        if body:
            recitals[num] = body

    pitfalls = guide.get("pitfalls", []) or []
    proportionality = (guide.get("proportionality", {}) or {}).get("tiers", []) or []
    applicability_rules = applic if isinstance(applic, list) else (applic.get("rules") or [])

    header = textwrap.dedent(
        f'''\
        """Generated EU AI Act corpus — DO NOT EDIT BY HAND.

        Regenerated via ``py -3.12 scripts/generate_ansvar_corpus.py`` from the
        Ansvar-Systems/EU_compliance_MCP snapshot. The upstream regulation
        text itself is public domain (EUR-Lex consolidated; Article 297 TFEU);
        the curated guide / applicability layers are Apache-2.0 licensed.

        Upstream SHAs (pinned at generation time):

            ansvar_ai_act_full.json         {_sha256(FULL_JSON)}
            ansvar_ai_act_guide.json        {_sha256(GUIDE_JSON)}
            ansvar_ai_act_applicability.json {_sha256(APPLIC_JSON)}

        Contents:

        * :data:`ARTICLE_FULL_TEXT`   — 113 articles + 13 annexes, full EUR-Lex prose.
        * :data:`ARTICLE_TITLE`       — per-article title.
        * :data:`ARTICLE_CHAPTER`     — per-article chapter assignment.
        * :data:`ART_3_DEFINITIONS`   — 68 Art. 3 terms (vs our hand-curated 31).
        * :data:`RECITALS`            — 181 recitals indexed by number.
        * :data:`PITFALLS`            — severity-rated failure-mode registry.
        * :data:`PROPORTIONALITY`     — 7-tier risk pyramid with key_articles per tier.
        * :data:`APPLICABILITY_RULES` — sector × subsector → basis_article rules.

        Consumed by:

        * ``app/data/kb_search.py``  — augments the BM25 corpus.
        * ``app/data/kb.py``         — augments thin obligation stubs.
        * ``app/data/definitions.py`` — back-fills missing Art. 3 terms.
        * ``app/engines/graph_rag.py`` — pitfalls surfaced in deterministic answers.
        * ``app/engines/scenario_classifier.py`` — applicability rules + tiers.
        """
        from __future__ import annotations

        '''
    )

    def _write_dict_str(name: str, mapping: dict, key_is_int: bool = False) -> str:
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

    def _write_dict_opt_str(name: str, mapping: dict[str, str | None]) -> str:
        lines = [f"{name}: dict[str, str | None] = {{"]
        for k in sorted(mapping.keys()):
            v = mapping[k]
            lines.append(f"    {k!r}: {v!r},")
        lines.append("}")
        return "\n".join(lines)

    def _write_list(name: str, items: list) -> str:
        # ``pprint`` gives valid Python literals (``True`` / ``False`` /
        # ``None``) where ``json.dumps`` would emit JS-style
        # ``true`` / ``false`` / ``null`` and break import.
        import pprint as _pprint  # noqa: PLC0415

        payload = _pprint.pformat(items, indent=2, width=88, sort_dicts=False)
        return f"{name}: list[dict] = {payload}"

    sections: list[str] = [header]
    sections.append(_write_dict_str("ARTICLE_FULL_TEXT", article_text))
    sections.append("")
    sections.append(_write_dict_str("ARTICLE_TITLE", article_title))
    sections.append("")
    sections.append(_write_dict_opt_str("ARTICLE_CHAPTER", article_chapter))
    sections.append("")
    sections.append(_write_dict_str("ART_3_DEFINITIONS", definitions))
    sections.append("")
    sections.append(_write_dict_str("RECITALS", recitals, key_is_int=True))
    sections.append("")
    sections.append(_write_list("PITFALLS", pitfalls))
    sections.append("")
    sections.append(_write_list("PROPORTIONALITY", proportionality))
    sections.append("")
    sections.append(_write_list("APPLICABILITY_RULES", applicability_rules))
    sections.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    print(
        f"Stats: articles={len(article_text)} definitions={len(definitions)} "
        f"recitals={len(recitals)} pitfalls={len(pitfalls)} "
        f"tiers={len(proportionality)} applicability={len(applicability_rules)}"
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
