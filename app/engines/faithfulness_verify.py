"""R313 — bounded faithfulness verification over the Stage-2 answer.

WHY THIS EXISTS
===============

R312 measured the answer-first Stage-2 framing (``REGENOLD_ANSWER_FIRST``)
against the refine-the-draft framing on 40 paired rows, graded by the grounded
Sonnet-5 judge:

    axis                    refine   answer-first   delta    per-row   p
    answer_correctness      0.475    0.575          +0.100   6/2/32    0.289
    reference_correctness   0.375    0.375           0.000   3/3/34    1.000
    citation_faithfulness   0.925    0.800          -0.125   0/5/35    0.062

The targeted axis moved the right way and a DIFFERENT one broke. The citation
regression is the strongest single signal in that round (0 wins to 5 losses),
and all five losses are one precise class — a claim ATTRIBUTED to a cited
provision that the provision's verbatim text does not support:

  * ``st_v4_001`` — Article 3 cited for deployer / emotion-recognition-system
    definitions; verbatim Article 3(1) only defines "AI system".
  * ``st_v4_006`` — Article 6 classification called automatic "without any
    further condition", ignoring the Article 6(3) derogations.
  * ``st_v4_019`` — Article 101 cited and then never described in the prose.
  * ``tp_v4_011`` — Article 6(2) mischaracterised as establishing an
    intended-purpose-over-commercial-label test; it says no such thing.
  * ``tp_v4_012`` — Article 6(3) credited with the documentation-before-market
    duty that actually belongs to Article 6(4).

So the deterministic draft was doing TWO jobs: it CAPS the answer (+0.100 when
removed) and it TETHERS the prose to the supplied text (-0.125 when removed).
R312's own verdict: do not remove the draft, DECOUPLE the two jobs — let the
model answer freely, then verify faithfulness against the verbatim text of each
cited provision. That is the bounded CoVe check R110 scaffolded and deferred on
latency grounds; R312 is the first hard evidence it is the load-bearing piece,
because it is precisely the failure the draft was silently preventing.

WHY IT CAN WORK WHERE AN INLINE SELF-CHECK CANNOT
=================================================

Four of the five failures are SUB-PROVISION misattribution (6(3) vs 6(4), 6(2)
mischaracterised, Article 3 vs Article 3(1)). ``app.data.provision_text``
resolves those distinctly — ``Art. 6(3)`` returns the derogation text and
``Art. 6(4)`` returns the documentation duty — so the verifier is handed the
exact discriminating evidence. A same-call self-check has no such second look:
the model would be grading text it just wrote, against context it already
attended to.

SAFETY — THIS PASS MAY ONLY SUBTRACT OR RE-ATTRIBUTE
====================================================

The wire ``references`` list is derived from the prose downstream (the route's
prose-named-ref pass and the R72 reconcile), so editing the answer is a
reference-affecting change. Every R142.1 lesson applies (the positional
over-citation clamp lost a live pairwise judge 11-0, p=0.001, by dropping GOLD).
The output is therefore rejected — original kept — unless ALL of:

  1. it is non-empty and retains at least ``_MIN_LENGTH_RATIO`` of the original
     length (a verifier that "repairs" an answer into a stub is a regression,
     not a fix — cf. R16/R49 "an over-broad answer beats an empty one");
  2. its citation set is a SUBSET of the original's (never a superset) — the
     pass may drop a mis-attributed cite, never invent one. legal_v2 scores
     reference_correctness as governing / (governing + supporting + wrong), so
     an added supporting ref is an arithmetic loss even when the prose is true;
  3. it still carries at least one citation when the original did;
  4. it carries no meta-commentary leak about the verification itself.

Any exception anywhere returns the original answer. The pass can no-op, or it
can delete/re-attribute an unsupported claim. It has no third behaviour.

DEFAULT OFF. Ships gated for the live A/B it owes (CLAUDE.md hard rule #6:
``evals.harness`` + the grounded judge is the merge gate, davidath is only the
regression guard and is byte-identical here BY CONSTRUCTION — the deterministic
bench runs ``provider=cli``, so Stage-2 never fires and this pass is
unreachable).
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

__all__ = [
    "extract_cited_refs",
    "faithfulness_verify_enabled",
    "build_ground_truth",
    "verify_and_repair",
]


# ── Env gates ────────────────────────────────────────────────────────────────

def faithfulness_verify_enabled() -> bool:
    """``REGENOLD_ANSWER_VERIFY`` — DEFAULT OFF, pending the live A/B.

    Fresh env read per call (R263.2 — a cached read makes a same-process
    two-arm A/B measure nothing).
    """
    return os.getenv("REGENOLD_ANSWER_VERIFY", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _max_refs() -> int:
    """How many cited provisions to supply verbatim text for (bounded)."""
    try:
        return max(1, min(12, int(os.getenv("REGENOLD_VERIFY_MAX_REFS", ""))))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_REFS


def _ref_chars() -> int:
    """Per-provision verbatim char budget."""
    try:
        return max(200, min(4000, int(os.getenv("REGENOLD_VERIFY_REF_CHARS", ""))))
    except (TypeError, ValueError):
        return _DEFAULT_REF_CHARS


_DEFAULT_MAX_REFS = 6
_DEFAULT_REF_CHARS = 900
# Reject a "repair" that guts the answer. 0.45 tolerates deleting a genuinely
# unsupported sentence or two out of a 3-5 sentence answer while catching the
# collapse-to-a-stub failure mode.
_MIN_LENGTH_RATIO = 0.45
_MIN_LENGTH_ABS = 80


# ── Citation extraction ──────────────────────────────────────────────────────
#
# Mirrors the shapes the post-Stage-2 hallucination guard already recognises in
# prose (``_PROSE_ARTICLE_RE`` / ``_PROSE_ANNEX_RE`` in the engine), plus the
# sub-provision forms the R312 failures actually turn on: ``Article 6(3)``,
# ``Article 6(3)(a)``, ``Article 3(1)`` and the dotted wire form ``Article 6.3``.

_ARTICLE_CITE_RE = re.compile(
    # ``Arts.`` is a real abbreviation in this corpus (the KB stubs write
    # "(Arts. 9-15)") and R307 had to teach the sentence splitter about it.
    # Missing it here would blind the subset guard to a swapped sibling.
    r"\bArt(?:s?\.|icles?|s)?\s*"
    r"(\d{1,3})"                                   # article number
    r"((?:\s*\(\s*\d{1,3}\s*\)|\s*\(\s*[a-z]{1,3}\s*\)|\.\d{1,3}|\.[a-z]{1,3}\b)*)",
    re.IGNORECASE,
)
_ANNEX_CITE_RE = re.compile(
    r"\bAnnexe?s?\s+([IVXLCDM]{1,7})"
    r"((?:\s*\(\s*\d{1,3}\s*\)|\s*\(\s*[a-z]{1,3}\s*\)|\.\d{1,3}|\.[a-z]{1,3}\b)*)",
    re.IGNORECASE,
)
_SUBPOINT_TOKEN_RE = re.compile(r"\(\s*([0-9a-z]{1,3})\s*\)|\.([0-9a-z]{1,3})\b", re.IGNORECASE)

# Plural enumerations ("Articles 9, 10 and 15", "Annexes IV and V"). The
# singular regexes above capture only the FIRST token of such a list, which
# would let the subset guard miss a swapped sibling ("Articles 9 and 10" ->
# "Articles 9 and 11"). Mirrors the engine's own _PROSE_ARTICLES_ENUM_RE.
_ARTICLES_ENUM_RE = re.compile(
    r"\bArticles\s+(\d{1,3}(?:\s*(?:,|and|or)\s+\d{1,3})+)", re.IGNORECASE
)
_ANNEXES_ENUM_RE = re.compile(
    r"\bAnnexes\s+([IVXLCDM]{1,7}(?:\s*(?:,|and|or)\s+[IVXLCDM]{1,7})+)",
    re.IGNORECASE,
)


def _canonical_subpoints(tail: str) -> list[str]:
    """Normalise a citation tail (``(3)(a)`` / ``.3.a``) to ``['3', 'a']``."""
    out: list[str] = []
    for m in _SUBPOINT_TOKEN_RE.finditer(tail or ""):
        tok = (m.group(1) or m.group(2) or "").strip().lower()
        if tok:
            out.append(tok)
    return out


def extract_cited_refs(text: str) -> list[str]:
    """Every Article/Annex citation in ``text``, most-specific form preserved.

    Returns canonical internal refs (``Art. 6(3)`` / ``Annex III(1)(c)``) in
    first-appearance order, deduplicated. Bare parents are RETAINED alongside
    their leaves: an answer that says "Article 6 classifies ... and Article 6(3)
    derogates" makes two distinct claims and both need checking.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()

    for m in _ARTICLE_CITE_RE.finditer(text):
        num = m.group(1)
        subs = _canonical_subpoints(m.group(2) or "")
        ref = "Art. " + num + "".join(f"({s})" for s in subs)
        if ref not in seen:
            seen.add(ref)
            found.append(ref)

    for m in _ANNEX_CITE_RE.finditer(text):
        roman = m.group(1).upper()
        subs = _canonical_subpoints(m.group(2) or "")
        ref = "Annex " + roman + "".join(f"({s})" for s in subs)
        if ref not in seen:
            seen.add(ref)
            found.append(ref)

    # Trailing members of a plural enumeration, which the singular passes above
    # capture only the head of.
    for m in _ARTICLES_ENUM_RE.finditer(text):
        for num in re.findall(r"\d{1,3}", m.group(1)):
            ref = f"Art. {num}"
            if ref not in seen:
                seen.add(ref)
                found.append(ref)
    for m in _ANNEXES_ENUM_RE.finditer(text):
        # Split on the separators rather than scanning for roman characters: a
        # case-insensitive character scan matches the "d" in "and" and would
        # invent an "Annex D".
        for token in re.split(r"\s*(?:,|and|or)\s*", m.group(1), flags=re.IGNORECASE):
            roman = token.strip()
            if not re.fullmatch(r"[IVXLCDM]{1,7}", roman, re.IGNORECASE):
                continue
            ref = f"Annex {roman.upper()}"
            if ref not in seen:
                seen.add(ref)
                found.append(ref)

    return found


def _citation_identity(text: str) -> set[str]:
    """The citation SET used for the subset guard (order-insensitive)."""
    return set(extract_cited_refs(text))


# ── Ground truth ─────────────────────────────────────────────────────────────

def build_ground_truth(refs: list[str], *, max_refs: int | None = None,
                       ref_chars: int | None = None) -> list[tuple[str, str]]:
    """Verbatim official text for each cited provision.

    For a SUB-provision citation (``Art. 6(3)``) the sibling context matters:
    tp_v4_012 credited Article 6(3) with a duty that belongs to Article 6(4), so
    a verifier shown only 6(3) can say "not supported" but cannot RE-ATTRIBUTE.
    We therefore also resolve the numbered siblings of a cited paragraph when
    budget allows, which is what lets the pass repair rather than merely delete.

    Never raises: an unresolvable ref is skipped.
    """
    limit = _max_refs() if max_refs is None else max_refs
    budget = _ref_chars() if ref_chars is None else ref_chars

    try:
        from app.data.provision_text import get_provision_text  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — no provision corpus ⇒ nothing to verify
        logger.debug("faithfulness: provision_text unavailable", exc_info=True)
        return []

    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(ref: str) -> None:
        if ref in seen or len(out) >= limit:
            return
        try:
            body = get_provision_text(ref)
        except Exception:  # noqa: BLE001 — a bad ref must never break the pass
            logger.debug("faithfulness: %s did not resolve", ref, exc_info=True)
            return
        if not body:
            return
        seen.add(ref)
        flat = " ".join(str(body).split())
        out.append((ref, flat[:budget]))

    for ref in refs:
        _add(ref)

    # R313.1 — the Neo4j Aura hierarchy as an ADDITIONAL evidence source.
    #
    # The graph holds 656 Paragraph + 416 Point nodes keyed at exactly the grain
    # these failures live at, so when a cited ARTICLE is bare ("Article 6") the
    # graph supplies its paragraph breakdown and the verifier can tell 6(2) from
    # 6(3) from 6(4). Strictly additive and de-duplicated against what
    # ``provision_text`` already resolved, and fail-soft: a disabled client or
    # an unreachable instance simply contributes nothing.
    try:
        from app.engines.kg_context import fetch_provision_hierarchy  # noqa: PLC0415

        bare = [r for r in refs if "(" not in r]
        for row in fetch_provision_hierarchy(bare):
            cite = str(row.get("cite") or "").strip()
            m_num = re.search(r"(\d{1,3})", cite)
            for unit in (row.get("units") or [])[:6]:
                num = str((unit or {}).get("num") or "").strip()
                body = " ".join(str((unit or {}).get("text") or "").split())
                if not (num and body and m_num):
                    continue
                sub_ref = f"Art. {m_num.group(1)}({num})"
                if sub_ref not in seen and len(out) < limit + 4:
                    seen.add(sub_ref)
                    out.append((sub_ref, body[:budget]))
    except Exception:  # noqa: BLE001 — the graph must never break the verifier
        logger.debug("faithfulness: kg hierarchy unavailable", exc_info=True)

    # Sibling paragraphs of any cited sub-provision, so a misattributed claim
    # can be re-pointed at the provision that actually carries it.
    for ref in list(refs):
        m = re.match(r"^(Art\.\s*\d{1,3})\((\d{1,3})\)$", ref.strip())
        if not m:
            continue
        parent, para = m.group(1), int(m.group(2))
        for sibling in (para - 1, para + 1):
            if sibling >= 1:
                _add(f"{parent}({sibling})")

    return out


# ── The prompt ───────────────────────────────────────────────────────────────

_VERIFY_SYSTEM = (
    "You are a meticulous EU AI Act citation checker. You are given a draft "
    "answer and the VERBATIM official text of each provision it cites. You "
    "return the corrected answer and nothing else."
)


def _build_verify_user(answer: str, question: str,
                       ground_truth: list[tuple[str, str]]) -> str:
    gt = "\n".join(f"[{ref}] {body}" for ref, body in ground_truth)
    return (
        f"QUESTION THE ANSWER MUST ADDRESS:\n{question}\n\n"
        f"DRAFT ANSWER:\n{answer}\n\n"
        f"VERBATIM OFFICIAL TEXT OF THE CITED PROVISIONS:\n{gt}\n\n"
        "TASK: check every claim the draft attributes to a cited provision "
        "against that provision's verbatim text above, then return the "
        "corrected answer.\n"
        "Apply exactly these repairs, in this order:\n"
        "1. RE-ATTRIBUTE: if a claim is true but credited to the wrong "
        "provision, and the verbatim text above shows which provision actually "
        "carries it, change the citation to that provision and keep the claim. "
        "(Example of the error class: crediting a documentation duty to Article "
        "6(3) when the verbatim text puts it in Article 6(4).)\n"
        "2. QUALIFY: if a claim overstates a provision by ignoring a condition, "
        "derogation or exception that the verbatim text states, add the missing "
        "qualifier in a few words rather than deleting the claim.\n"
        "3. DELETE: if a claim is attributed to a cited provision and NO "
        "verbatim text above supports it, delete that clause or sentence.\n"
        "4. DESCRIBE OR DROP: if the draft cites a provision without ever "
        "saying what it requires, either state in a few words what the verbatim "
        "text says it requires, or remove that bare citation.\n\n"
        "HARD CONSTRAINTS:\n"
        "- Do NOT introduce any Article or Annex that the draft does not "
        "already cite. Correcting a citation to a provision shown above is "
        "allowed; adding a new one is not.\n"
        "- Do NOT rewrite, reorder, restyle, expand or shorten anything the "
        "verbatim text supports. Leave every supported sentence exactly as it "
        "is. If nothing is wrong, return the draft unchanged, character for "
        "character.\n"
        "- Keep the draft's voice: formal third-person regulatory prose, no "
        "em-dashes, en-dashes or ellipses.\n"
        "- Output ONLY the corrected answer text. No preamble, no explanation "
        "of what you changed, no headings, no list of corrections, no quotes "
        "around the answer.\n"
    )


# ── Output validation ────────────────────────────────────────────────────────

_META_LEAK_MARKERS = (
    "corrected answer",
    "the draft",
    "verbatim text above",
    "i have corrected",
    "i corrected",
    "no corrections",
    "unchanged",
    "as requested",
    "here is the",
    "changes made",
    "verification",
)


def _looks_like_meta(text: str) -> bool:
    """Reject an output that talks ABOUT the verification instead of answering.

    Only the opening is inspected: "unchanged" or "verification" can legitimately
    appear deep inside a compliance answer (Article 72 post-market monitoring
    prose, for one), but a leak announces itself in the first clause.
    """
    head = " ".join(str(text or "").split())[:160].lower()
    return any(marker in head for marker in _META_LEAK_MARKERS)


def _accept(original: str, candidate: str) -> tuple[bool, str]:
    """Gate the verifier's output. Returns ``(accepted, reason)``."""
    cand = (candidate or "").strip()
    orig = (original or "").strip()
    if not cand:
        return False, "empty"
    if _looks_like_meta(cand):
        return False, "meta_leak"
    if len(cand) < _MIN_LENGTH_ABS and len(orig) >= _MIN_LENGTH_ABS:
        return False, "too_short_abs"
    if orig and len(cand) < _MIN_LENGTH_RATIO * len(orig):
        return False, "too_short_ratio"

    orig_cites = _citation_identity(orig)
    cand_cites = _citation_identity(cand)
    added = cand_cites - orig_cites
    if added:
        # A re-attribution to a SIBLING of an already-cited article is the one
        # repair we explicitly asked for, so it is not "adding a citation".
        def _parent(ref: str) -> str:
            return re.sub(r"\(.*$", "", ref).strip()
        orig_parents = {_parent(r) for r in orig_cites}
        if any(_parent(r) not in orig_parents for r in added):
            return False, "citation_added"
    if orig_cites and not cand_cites:
        return False, "citations_stripped"
    return True, "ok"


# ── Public entry point ───────────────────────────────────────────────────────

def verify_and_repair(
    answer: str,
    question: str,
    *,
    complete_fn=None,
) -> tuple[str, str]:
    """Verify ``answer`` against the verbatim text of the provisions it cites.

    Returns ``(answer, action)``. ``action`` is one of::

        disabled          gate off
        no_citations      the answer cites nothing to check
        no_ground_truth   nothing resolved to verbatim text
        call_failed       the provider returned nothing
        unchanged         the verifier returned the draft as-is
        repaired          a claim was re-attributed / qualified / deleted
        rejected:<why>    the output failed a safety gate; original kept
        error             an exception; original kept

    ``complete_fn`` is injected for tests; production passes the engine's
    wrapper/Anthropic completion helper.
    """
    try:
        if not faithfulness_verify_enabled():
            return answer, "disabled"
        if not (answer or "").strip():
            return answer, "no_citations"

        refs = extract_cited_refs(answer)
        if not refs:
            return answer, "no_citations"

        ground_truth = build_ground_truth(refs)
        if not ground_truth:
            return answer, "no_ground_truth"

        if complete_fn is None:
            from app.engines._graph_rag_impl import (  # noqa: PLC0415
                _stage2_complete,
            )
            complete_fn = _stage2_complete

        user = _build_verify_user(answer, question, ground_truth)
        out = complete_fn(
            system=_VERIFY_SYSTEM,
            user=user,
            # A verification pass rewrites at most a couple of clauses, so it
            # never needs a larger envelope than the answer it is checking.
            max_tokens=max(512, min(2048, len(answer) // 2 + 512)),
            temperature=0.0,
            stage_name="Stage 3 (Faithfulness verify)",
        )
        if not out or not str(out).strip():
            return answer, "call_failed"

        candidate = str(out).strip()
        accepted, reason = _accept(answer, candidate)
        if not accepted:
            logger.info("faithfulness_verify rejected output: %s", reason)
            return answer, f"rejected:{reason}"

        if " ".join(candidate.split()) == " ".join(answer.split()):
            return answer, "unchanged"
        return candidate, "repaired"
    except Exception:  # noqa: BLE001 — a guard must never break Stage-2
        logger.debug("faithfulness_verify failed", exc_info=True)
        return answer, "error"
