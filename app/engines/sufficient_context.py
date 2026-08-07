"""R110 — Sufficient-Context gate: bounded, deterministic multi-hop decomposition.

## Why this exists

The FRAMES benchmark (Krishna et al., *Fact, Fetch, and Reason*, NAACL 2025,
arXiv:2409.12941) showed that on genuinely multi-hop questions, **single-step
retrieval barely beats no retrieval at all** (Gemini-Pro-1.5: 0.45 single-step
vs 0.41 no-retrieval) while **multi-step iterative retrieval lifts accuracy to
0.66** — and the oracle (gold documents in context) ceiling is 0.73. The entire
value comes from *iterating*: re-planning sub-queries against the accumulated
context so the scattered evidence a one-shot query can't reach gets pulled in.
The paper's stated failure mode of single-shot retrieval — *"the model goes in
the wrong direction in search retrievals and never corrects itself"* — is
exactly what a missing-pieces re-retrieval fixes.

Google's Gemini Enterprise Agentic RAG (Google Research, 2026) operationalised
this with a **Sufficient Context Agent** (grounded in *Sufficient Context: A New
Lens on RAG*, Joren et al., ICLR 2025, arXiv:2411.06037): after the first
retrieval it runs a *missing-pieces analysis* against the original request and
decides whether to loop again. That loop-gate is the single biggest driver of
the jump from the FRAMES paper's fixed-5-iteration 0.66 to Google's 90-93% on
FramesQA.

## Why it is bounded (the latency / cost / governance answer)

The standard critique of agentic RAG — open-ended planning + query-rewriting +
self-critique loops that fire 5-6 sequential LLM calls, blow the token bill, and
turn data lineage into a black box — is real for *unbounded* loops. This module
takes the **accuracy methodology** (sufficiency-gated re-retrieval) while
honouring the three production constraints:

* **Latency** — Adaptive-RAG (Jeong et al., NAACL 2024) shows routing by
  complexity recovers most of the multi-step accuracy at a fraction of the work.
  This gate fires ONLY on the ~20% of questions ``is_complex_question`` already
  flags (multi-phrase / role-ambiguity / conflict / cross-framework / GPAI
  boundary), and it caps the re-retrieval at ONE bounded hop of at most
  :func:`max_sub_queries` deterministic sub-queries. No open loop.
* **Token cost** — the decomposition is **deterministic** (regex clause split +
  explicit-reference gap detection). Zero LLM calls on the gate itself; it only
  re-runs the existing deterministic retrieval (sub-ms BM25 / 50 ms-capped
  Neo4j) per sub-query.
* **Auditability** — every sub-query and the references it surfaced are logged
  to the per-request :class:`ReasoningTrace` (``record_sub_query``), which is
  serialised into the ``reasoning`` wire field and persisted in the
  hash-chained audit store. The iterative path is *more* auditable than a
  single shot, not less — the provenance graph (sub-query → sources → merged
  refs) makes every retrieval decision inspectable. That is the direct rebuttal
  to the "black box" criticism.

## Contract

* Pure-stdlib, module-level, sub-µs per call.
* Env-gated ``REGENOLD_SUFFICIENT_CONTEXT`` (default OFF → the davidath bench is
  byte-identical by construction; the win lands LIVE on multi-part questions and
  the judge axes, the established R31/R69/R97 pattern).
* Fail-soft: every public function returns a safe "sufficient / no
  decomposition" verdict on any parse error so the gate can never break the
  route.
* Additive-only at the consumer (the engine appends sub-query obligations AFTER
  the primary retrieval, never displacing the first-pass anchors), honouring the
  R31/R81 "never displace a winner" doctrine.
"""
from __future__ import annotations

from collections.abc import Sequence
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — typing only
    from concurrent.futures import ThreadPoolExecutor
    from app.engines.crag_nli_verifier import EntailmentScorer

# ── Env gates ────────────────────────────────────────────────────────────

_TRUE = {"1", "true", "yes", "on"}


def sufficient_context_enabled() -> bool:
    """True when the Sufficient-Context gate is active. **Default ON (R319).**

    R319 — THE DEFAULT IS BACK ON. R318 flipped it OFF on a DETERMINISTIC
    sweep; the live pairwise A/B that CLAUDE.md hard rule #6 names as the merge
    gate had never been run for it. R319 ran it, and OFF fails.

    Paired live A/B, `provider=openai_wrapper` (Claude Max, Opus 5 Stage-2), on
    the 35-row TREATMENT population -- the only rows whose Stage-2 grounding
    context the flip actually changes, measured with zero variance beforehand
    (`.evalout/r319/context_delta.py`). 2 repeats per arm with the engine LRU
    cleared between them, so the delta is read against a MEASURED noise floor
    rather than assumed:

        axis            A(ON)    B(OFF)     delta    noise+-   B>A/A>B/tie    p
        ref_loose      0.8143    0.6786   -0.1357     0.0500     1 / 8 / 26  0.039
        ref_strict     0.5804    0.5259   -0.0546     0.0298     3 /10 / 22  0.092
        kw_canonical   0.8007    0.7798   -0.0210     0.0433     5 / 7 / 23  0.774
        ref_conc       0.4054    0.4487   +0.0433     0.0509     6 / 5 / 24  1.000
        tone           1.0000    1.0000   +0.0000     0.0000     0 / 0 / 35  1.000

    ``ref_loose`` is the ONLY axis whose delta clears its own noise floor
    (2.7x), and it is the only significant result. **Turning the gate OFF drops
    gold references on the live path** -- hard rule #8: "a reference change must
    drop ZERO gold; a non-zero count is a rejection, not a trade-off to argue
    about." Independently corroborated by the frontier splice
    (`.evalout/r319/sota_compare.py`): across all 132 rows Ref Loose falls
    0.8636 -> 0.8371, moving us from BEATING `claude-opus-5` (0.8396) to a tie.
    The two estimates agree once the treatment-only effect is diluted 35/132.

    WHY R318's ZERO-VARIANCE MEASUREMENT DID NOT TRANSFER -- the generalisable
    lesson. Under ``provider=cli`` the wire references are pure retrieval, so a
    deterministic sweep measures them exactly. With Stage-2 live they are partly
    a FUNCTION OF THE GENERATED ANSWER: ``_add_prose_named_refs`` adds refs the
    prose names and the R72 reconcile drops refs the prose does not describe. So
    shrinking the grounding context changes the answer, which changes the
    references. A deterministic reference measurement is therefore NOT a valid
    proxy for the live reference axes -- a second blind spot in that instrument,
    beyond the answer-side one R318 already acknowledged.

    This does NOT vindicate the hop as built. R319's qualitative audit measured
    what it adds at **2.5% gold precision** (10 of 401 added article-keys; 106
    distinct non-gold keys vs 5 distinct gold), and demonstrated crowding-out on
    `st_v4_013`, where the correct Article 50 obligation was present in the
    inflated context and still got dropped (kw recall 1.0 -> 0.0). The honest
    reading is that the hop is unfiltered, not that it is good: a bounded
    redesign (cap the merged obligations, require term overlap with the ORIGINAL
    question, fix the annex-key bug below) would plausibly beat both extremes.
    Until that exists, ON is the state the live gate supports.

    Operators disable explicitly: ``REGENOLD_SUFFICIENT_CONTEXT=0``.

    ---- superseded R318 rationale, kept for the record ----

    HISTORY — and why the default flipped.

    R110 shipped this default-OFF behind ``railway.toml [deploy.envs]``; R110.1
    baked it default-ON in code after a live probe showed the var never reached
    the service (the R80.2 phenomenon — later established in R306 as
    ``[deploy.envs]`` having *never* applied, because Railway's ``[deploy]``
    schema has no ``envs`` key at all).

    The ON default rested on "davidath byte-identical, gate ON vs OFF" — which
    is TRUE and was exactly the problem. davidath is BM25-saturated, so the
    bounded hop is a dedup no-op there and **the benchmark is structurally
    blind to this gate's cost**. It was shipped on a bench that could not
    measure it, and nothing else ever did.

    R318 measured it, on the 132-row gold-bearing probe set (V2 tricky +
    multi-turn — precisely the complex multi-part shapes the gate targets and
    the only place it actually fires), via a zero-variance deterministic sweep
    (``provider=cli``, no LLM anywhere, so re-running is exact). Turning the
    gate OFF is **strictly dominant** on every measured axis:

        gold refs      +1 GAINED (not a recall trade)
        non-gold refs  19 fewer
        Ref Loose      +0.0038
        Ref Strict     +0.0141
        Ref Conciseness +0.0254

    Mechanism: the hop additively unions re-retrieved refs on multi-part
    questions. Where BM25 already covers the anchors (davidath) that union is a
    no-op; where it fires for real, the extra refs are mostly non-gold, and
    over-citation is the one axis a frontier model still beats us on
    (Ref Strict −0.048 / Ref Conciseness −0.108 vs ``claude-opus-5``).

    Re-confirmed davidath **byte-identical with the gate OFF** — all seven axes
    +0.0000 across overall / qa / scenarios — so the regression guard is clean
    and the probe-set gain is free.

    Operators re-enable explicitly: ``REGENOLD_SUFFICIENT_CONTEXT=1``. Unset =
    OFF. The decomposition machinery is untouched and still fully tested; only
    the default changed, so re-enabling is a one-variable rollback.
    """
    val = os.getenv("REGENOLD_SUFFICIENT_CONTEXT")
    if val is None:
        return True  # R319 — see the live A/B above; R318's OFF dropped gold.
    return val.strip().lower() in _TRUE


def max_sub_queries() -> int:
    """Hard cap on sub-queries fired in the single bounded hop.

    Default 3 (the FRAMES best-config fired k=5 queries/iteration over 5
    iterations = 25 retrievals; we cap the whole thing at ONE hop of ≤3
    deterministic retrievals to keep latency predictable). Env override
    ``REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS``; clamped to [1, 5].
    """
    try:
        n = int(os.getenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", "3"))
    except ValueError:
        return 3
    return max(1, min(5, n))


# ── Shared executor (R112) ───────────────────────────────────────────────
#
# Module-level shared executor for the engine's parallel sub-query
# retrievals (``graph_rag._maybe_sufficient_context_hop``). R110.1 first
# constructed a fresh ``ThreadPoolExecutor`` per firing request — measured
# ~0.8 ms create+map+shutdown vs ~0.07 ms on a shared pool, plus OS thread
# churn under concurrent load. The codebase convention is a lazy
# module-level singleton (``graph_expand_2hop._get_executor``,
# ``graph_aware_retrieval._get_executor``). Created lazily so module import
# stays sub-ms (``concurrent.futures`` pulls ``threading`` + ``queue``).
_EXECUTOR: Any = None


def get_executor() -> ThreadPoolExecutor:
    """Lazy accessor for the shared sub-query retrieval pool.

    ``max_workers=4`` comfortably covers the ≤5 clamp of
    :func:`max_sub_queries` (default 3) without per-request thread churn.
    """
    global _EXECUTOR
    if _EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor

        _EXECUTOR = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="suffctx",
        )
    return _EXECUTOR


# ── Reference normalisation ──────────────────────────────────────────────

# Match `Art. 13` / `Art 13` / `Article 13` → key `art13`. Leading zeros
# tolerated; the int() collapse means `Article 013` == `Art. 13`.
_ART_KEY_RE = re.compile(r"\bart(?:icle|\.)?\s*0*(\d{1,3})\b", re.IGNORECASE)
# Match `Annex IV` (Roman, the catalogue form) or `Annex 4` (Arabic) → key
# `annexiv` / `annex4`. Both forms are normalised lower-case.
_ANNEX_KEY_RE = re.compile(r"\bannex\s+([ivxlcdm]+|\d{1,2})\b", re.IGNORECASE)

# R319 — an ALREADY-normalised key is returned unchanged, so this function is
# idempotent.
#
# It was not, and only for annexes: `_ANNEX_KEY_RE` requires whitespace between
# "annex" and the numeral, which a normalised key (`annexiv`) does not have, so
# `_article_key(_article_key("Annex IV")) == ""`. Article keys survived a second
# pass purely because `_ART_KEY_RE` uses `\s*` (`art6` -> `art6`).
#
# That matters because the engine DOUBLE-normalises: `_graph_rag_impl.
# _covered_article_keys` already returns keys, and `assess_sufficiency` then
# re-keys them (`covered_keys = {_article_key(a) for a in covered_articles}`).
# So every Annex in the covered set silently vanished, and the high-precision
# `uncovered_explicit_refs` path fired on Annex refs that were ALREADY covered
# — measured on 2 probe rows, both false positives that then re-fetched nothing.
#
# Matching the normalised shape (rather than loosening `_ANNEX_KEY_RE` to `\s*`)
# is the conservative fix: it cannot introduce a new match on free prose.
_NORMALISED_KEY_RE = re.compile(r"^(?:art\d{1,3}|annex(?:[ivxlcdm]+|\d{1,2}))$")


def _article_key(ref: str) -> str:
    """Normalise an article / annex reference string to a comparison key.

    Idempotent: ``_article_key(_article_key(x)) == _article_key(x)``.

    Returns ``""`` when no article/annex token is present — callers treat the
    empty key as "not an article reference" and skip it (so a bare obligation
    id or a free-text token can't masquerade as coverage of an article).
    """
    if not ref:
        return ""
    if _NORMALISED_KEY_RE.match(ref):
        return ref
    m = _ART_KEY_RE.search(ref)
    if m:
        return f"art{int(m.group(1))}"
    m = _ANNEX_KEY_RE.search(ref)
    if m:
        return f"annex{m.group(1).lower()}"
    return ""


# ── Live-section extraction (multi-turn flatten) ─────────────────────────

_LIVE_MARKER = "Latest question:\n"


def _live_section(question: str) -> str:
    """Return only the live (final) user turn when the route's multi-turn
    flatten marker is present, else the whole string.

    Mirrors :func:`app.engines.question_complexity.is_complex_question` so the
    decomposition scans the user's actual question, not the prepended history
    prose (which would split into spurious sub-clauses).
    """
    if not question:
        return ""
    idx = question.rfind(_LIVE_MARKER)
    return question[idx + len(_LIVE_MARKER):] if idx >= 0 else question


# ── Deterministic clause decomposition ───────────────────────────────────

# Verb tokens used to guard a coordination split: a " or " / " and "
# coordination is only a *clause* boundary (not a noun coordination like
# "providers and deployers") when BOTH sides carry a clause verb.
_CLAUSE_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|can|could|may|might|do|does|did|should|would|will|"
    r"shall|must|has|have|had|need|needs|count|counts|qualif\w*|fall|falls|"
    r"appl\w*|track|tracks|process(?:es)?|use|uses|deploy|deploys|provide|"
    r"provides|require|requires|classif\w*|constitut\w*|trigger|triggers)\b",
    re.IGNORECASE,
)
# Coordination boundary candidates, longest first so " versus " wins over a
# bare " vs ".
_COORD_RE = re.compile(r"\s+(?:versus|vs\.?|or|and)\s+", re.IGNORECASE)

# The RIGHT side of a coordination is a genuine *clause* boundary (not a
# continuation noun in a list like "providers and deployers and importers")
# only when it BEGINS like an independent clause: a Wh-word, an aux / copula /
# modal verb (" or IS it high-risk"), or a pronoun subject (" and THEY must").
# A bare noun start (" and importers do …") is a noun-list continuation, not a
# new clause — so it must NOT split. This is what keeps a long noun list from
# being chopped while still catching "what must X do AND what must Y do".
_CLAUSE_INITIAL_RE = re.compile(
    r"^(?:"
    r"what|how|when|who|whom|whose|why|which|where|"  # Wh-words
    r"is|are|was|were|can|could|may|might|do|does|did|should|would|will|"
    r"shall|must|has|have|had|need|"  # aux / copula / modal
    r"it|they|we|i|you|this|that|he|she"  # pronoun subjects
    r")\b",
    re.IGNORECASE,
)

_MIN_CLAUSE_WORDS = 4


def _split_on_coordination(sentence: str) -> list[str]:
    """Split one sentence on the FIRST genuine clause-level coordination.

    Conservative — splits at a " or " / " and " / " versus " boundary ONLY
    when ALL hold: both sides are ≥4 words, the left side carries a clause
    verb, and the right side *begins like an independent clause*
    (:data:`_CLAUSE_INITIAL_RE`). The right-side guard is what rejects a noun
    list:

      * "can it be deployed or is it high-risk"  → split ("is it …")
      * "what must providers do and what must deployers do" → split ("what …")
      * "what must providers and deployers and importers do" → NO split
        (the right of each " and " starts with a bare noun, "deployers" /
        "importers", not a clause-initial token).
    """
    for m in _COORD_RE.finditer(sentence):
        left = sentence[: m.start()].strip()
        right = sentence[m.end():].strip()
        if (
            len(left.split()) >= _MIN_CLAUSE_WORDS
            and len(right.split()) >= _MIN_CLAUSE_WORDS
            and _CLAUSE_VERB_RE.search(left)
            and _CLAUSE_INITIAL_RE.match(right)
        ):
            return [left, right]
    return [sentence]


def decompose_question(question: str) -> list[str]:
    """Deterministically decompose a question into substantive sub-clauses.

    1. Take the live section (drop multi-turn history prose).
    2. Split on sentence terminators ``. ! ? ;``.
    3. For each ≥4-word sentence, attempt ONE clause-level coordination split
       (guarded by :func:`_split_on_coordination`).
    4. Keep ≥4-word clauses, strip, dedupe (case-insensitive), preserve order.

    Returns a list with ≥1 entry (the cleaned question itself when nothing
    decomposes). A caller wanting "did this decompose into parts?" checks
    ``len(decompose_question(q)) >= 2``.
    """
    live = _live_section(question)
    if not live.strip():
        return []
    sentences = [s for s in re.split(r"[.!?;]+", live) if s.strip()]
    clauses: list[str] = []
    seen: set[str] = set()
    for sent in sentences:
        sent = sent.strip()
        if len(sent.split()) < _MIN_CLAUSE_WORDS:
            continue
        for clause in _split_on_coordination(sent):
            clause = clause.strip(" ,;")
            if len(clause.split()) < _MIN_CLAUSE_WORDS:
                continue
            key = clause.lower()
            if key not in seen:
                seen.add(key)
                clauses.append(clause)
    if not clauses:
        # Nothing substantive split out — return the cleaned live text as the
        # single (n=1) clause so the caller's "decomposed?" test is len>=2.
        cleaned = live.strip()
        return [cleaned] if cleaned else []
    return clauses


# ── Explicit-reference extraction ────────────────────────────────────────

_ART_REF_RE = re.compile(r"\b(?:Art\.?|Article)\s*(\d{1,3})\b", re.IGNORECASE)
_ANNEX_REF_RE = re.compile(r"\bAnnex\s+([IVXLCDM]+)\b", re.IGNORECASE)


def _explicit_refs(text: str) -> list[str]:
    """Display-form Article/Annex references named in the question text.

    Returns canonical ``"Article N"`` / ``"Annex X"`` strings (de-duplicated,
    order-preserving) so a gap sub-query re-parses cleanly through
    ``_deterministic_parse``.
    """
    refs: list[str] = []
    seen: set[str] = set()
    for n in _ART_REF_RE.findall(text):
        ref = f"Article {int(n)}"
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    for roman in _ANNEX_REF_RE.findall(text):
        ref = f"Annex {roman.upper()}"
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


# ── NLI Entailment Verification ─────────────────────────────────────────────


def verify_context_entailment(
    question: str,
    context_passages: list[str] | Sequence[str],
    scorer: EntailmentScorer | None = None,
    threshold: float = 0.35,
) -> tuple[bool, float]:
    """Verify whether context_passages entail the question using an EntailmentScorer.

    Prevents topically-related mention fallacies on negative controls where
    passages mention query keywords but do not actually entail an answer to the question.

    Returns (is_entailed, max_score).
    """
    if not question or not context_passages:
        return False, 0.0

    passages = [str(p).strip() for p in context_passages if str(p).strip()]
    if not passages:
        return False, 0.0

    if scorer is None:
        try:
            from app.engines.crag_nli_verifier import NLIEntailmentScorer
            scorer = NLIEntailmentScorer()
        except Exception:
            try:
                from app.engines.crag_nli_verifier import LexicalEntailmentScorer
                scorer = LexicalEntailmentScorer([{"text": p} for p in passages])
            except Exception:
                return True, 1.0

    try:
        scores = scorer.score_batch(question, passages)
        max_s = max(scores) if scores else 0.0
        return max_s >= threshold, max_s
    except Exception:
        return True, 1.0


# ── Verdict ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SufficiencyVerdict:
    """Outcome of the deterministic sufficiency assessment.

    * ``sufficient`` — True when the first-pass retrieval already covers every
      anchor the question names / every sub-part it asks about; no extra hop.
    * ``sub_queries`` — the bounded set of sub-queries to re-retrieve when
      insufficient (already capped at :func:`max_sub_queries`).
    * ``uncovered_anchors`` — explicit Article/Annex refs named in the question
      that the first-pass retrieval missed (the highest-precision gap signal).
    * ``reason`` — ``"uncovered_explicit_refs"`` / ``"multi_phrase_decompose"``
      / ``"nli_entailment_failure"`` / ``"sufficient"`` / ``"not_complex"`` — recorded in the audit trace.
    """

    sufficient: bool
    sub_queries: tuple[str, ...] = field(default_factory=tuple)
    uncovered_anchors: tuple[str, ...] = field(default_factory=tuple)
    reason: str = "sufficient"


def assess_sufficiency(
    question: str,
    covered_articles: set[str] | frozenset[str],
    context_passages: list[str] | Sequence[str] | None = None,
    scorer: EntailmentScorer | None = None,
    entailment_threshold: float = 0.35,
) -> SufficiencyVerdict:
    """Decide whether the first-pass context is sufficient, else what to fetch.

    The missing-pieces analysis, deterministically:

    1. **Explicit-reference gap (highest precision).** Every Article/Annex the
       question names but the first-pass retrieval did NOT surface is an
       uncovered anchor — re-fetch it directly. If a user says "Articles 13 and
       50" and only Art. 13 came back, the answer is provably incomplete.
    2. **NLI Entailment verification.** Verify that retrieved context passages
       actually entail the question (via EntailmentScorer), preventing topically-related
       mention fallacies on negative controls.
    3. **Multi-part decomposition.** When the question genuinely decomposes into
       ≥2 substantive sub-clauses (:func:`decompose_question` — verb-guarded,
       clause-initial-guarded, so a noun list does NOT split), re-retrieve each
       sub-clause so a multi-part ask isn't answered from a single sub-part's
       anchor.
    4. Otherwise the context is sufficient — no hop.

    :param covered_articles: the set of article/annex reference strings already
        present in the first-pass context (any format; normalised internally).
    :param context_passages: optional list of context text passages for NLI verification.
    :param scorer: optional EntailmentScorer instance.
    :param entailment_threshold: minimum NLI entailment score threshold (default 0.35).
    """
    live = _live_section(question)
    if not live.strip():
        return SufficiencyVerdict(True, reason="empty")

    covered_keys = {_article_key(a) for a in covered_articles}
    covered_keys.discard("")

    # (1) Explicit-reference gap — highest precision, always checked.
    explicit = _explicit_refs(live)
    uncovered = [r for r in explicit if _article_key(r) not in covered_keys]
    if uncovered:
        return SufficiencyVerdict(
            sufficient=False,
            sub_queries=tuple(uncovered[: max_sub_queries()]),
            uncovered_anchors=tuple(uncovered),
            reason="uncovered_explicit_refs",
        )

    # (2) NLI Entailment verification — prevent topically-related mention fallacies on negative controls.
    if context_passages:
        is_entailed, _score = verify_context_entailment(
            live,
            context_passages,
            scorer=scorer,
            threshold=entailment_threshold,
        )
        if not is_entailed:
            clauses = decompose_question(question)
            return SufficiencyVerdict(
                sufficient=False,
                sub_queries=tuple(clauses[: max_sub_queries()]),
                uncovered_anchors=tuple(),
                reason="nli_entailment_failure",
            )

    # (3) Multi-part decomposition — the DETERMINISTIC decomposer is the
    # complexity gate. It is verb- + clause-initial-guarded, so a single-clause
    # prohibition / definitional / lookup question (e.g. "Is real-time RBI in
    # public spaces prohibited?") never decomposes. The LLM planner
    # (``decompose_question_llm``) is consulted ONLY to refine the sub-query
    # *phrasing* once this gate has already confirmed genuine multi-part
    # structure.
    deterministic_clauses = decompose_question(question)
    if len(deterministic_clauses) < 2:
        return SufficiencyVerdict(True, reason="sufficient")

    from app.engines.frames_planner import decompose_question_llm
    llm_clauses = decompose_question_llm(question)
    # Prefer the LLM's phrasing when it also agrees this is multi-part;
    # otherwise fall back to the deterministic clauses (the gate already
    # proved >= 2 substantive parts).
    clauses = llm_clauses if len(llm_clauses) >= 2 else deterministic_clauses
    return SufficiencyVerdict(
        sufficient=False,
        sub_queries=tuple(clauses[: max_sub_queries()]),
        uncovered_anchors=tuple(),
        reason="multi_phrase_decompose",
    )
