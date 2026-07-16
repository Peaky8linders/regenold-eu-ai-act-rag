"""R276-D2 — the ``Art.`` complexity bug.

The route normalises conversation anchors to ``Art. N`` form and prepends
``[Context anchors — articles: Art. 13, Art. 26; roles: deployer]`` to the
live question (``regenold.py::_extract_conversation_anchors``). The
complexity scan then read that injected metadata as if it were user text,
which corrupted the tier decision in BOTH directions:

* it ADDED complexity — the naive ``re.split(r"[.!?]+")`` read the period in
  ``Art.`` as a sentence end ⇒ two ≥4-word segments ⇒ ``_is_multi_phrase``.
  Both tiers are ``claude-opus-4-8`` (R271) and differ ONLY by the thinking
  budget, so this bought a 4000-token extended-thinking budget and bought
  nothing back (R271 measured thinking-present at ~23% slower).
* it SUPPRESSED complexity — sitting at position 0, the prefix blocked the
  ``^``-anchored ``_SHORT_COREFERENT_RE``, silently downgrading genuine
  short follow-ups. This direction costs answer correctness.

**The fix is the anchor-prefix strip ONLY.** Making ``_is_multi_phrase``
abbreviation-aware is the obvious companion fix and is a TRAP — neither
splitter in the repo is correct for a question, and both trade a
latency-only false fire for a correctness-costing false miss. The tests
under "the trap" pin that evidence; read them before "completing" this fix.

Why each test matters (each must fail if the behaviour regresses):

* the fix must kill the FALSE fire, and restore the SUPPRESSED signal;
* it must NOT kill genuine multi-phrase detection — the expensive
  direction. Those guards assert ``_is_multi_phrase`` DIRECTLY: routed
  through ``is_complex_question`` they passed via ``_ROLE_AMBIGUITY_RE``
  and could not fail (Rule 9);
* davidath byte-identity: the bench gate assumes this fix cannot move the
  deterministic scorecard. Pinned so the assumption is enforced, not
  trusted.
"""
from __future__ import annotations

import importlib
import json
import pathlib

import pytest

import app.engines.question_complexity as qc

_ANCHOR = "[Context anchors — articles: Art. 13, Art. 26; roles: deployer]"
_LIVE = (
    "What are the transparency obligations for a deployer of an "
    "emotion recognition system?"
)
_HIST = "User: Tell me about Art. 13.\nAssistant: It covers transparency."


def _reload(monkeypatch, value: str):
    """Reload the module under a given flag value.

    The flag is read per-call, but reloading also re-binds the module-level
    regexes so the test exercises a clean import the way a worker would.
    """
    monkeypatch.setenv("REGENOLD_COMPLEXITY_ABBREV_FIX", value)
    importlib.reload(qc)
    return qc


@pytest.fixture(autouse=True)
def _restore():
    yield
    importlib.reload(qc)


# ── the bug itself ──────────────────────────────────────────────────────

def test_anchor_prefix_falsely_fires_complexity_when_fix_disabled(monkeypatch):
    """Pins the BUG so the fix cannot be silently reverted to a no-op.

    With the fix off, the injected anchor line alone flips a simple
    question to complex.
    """
    m = _reload(monkeypatch, "0")
    assert m.is_complex_question(_LIVE, 1) is False, "plain Q is not complex"
    assert m.is_complex_question(f"{_ANCHOR}\n{_LIVE}", 3) is True, (
        "baseline: the anchor prefix falsely fires complexity"
    )


def test_anchor_prefix_no_longer_fires_complexity(monkeypatch):
    """The fix: prepending OUR OWN metadata must not change the tier."""
    m = _reload(monkeypatch, "1")
    assert m.is_complex_question(f"{_ANCHOR}\n{_LIVE}", 3) is False, (
        "anchor prefix must not make a simple question complex"
    )


def test_anchor_prefix_is_tier_neutral(monkeypatch):
    """The invariant, stated directly: the prefix is metadata WE inject, so
    it must never change the routing decision for the same live question."""
    m = _reload(monkeypatch, "1")
    assert m.is_complex_question(f"{_ANCHOR}\n{_LIVE}", 3) == m.is_complex_question(
        _LIVE, 3
    )


# ── the flatten path was NOT affected (plan's table row 4 is wrong) ─────

def test_flatten_path_was_never_affected(monkeypatch):
    """R60.1's ``rfind("Latest question:\\n")`` already skipped the prefix.

    Measured, contra the R276 plan's table: only the marker-less denoised
    path (``regenold.py`` ~:4587) ever carried the prefix into the scan.
    Pinned so a future refactor of the marker logic cannot quietly widen
    the blast radius back out.
    """
    flat = f"{_ANCHOR}\n\nConversation so far:\n{_HIST}\n\nLatest question:\n{_LIVE}"
    for value in ("0", "1"):
        m = _reload(monkeypatch, value)
        assert m.is_complex_question(flat, 3) is False, (
            f"flatten path must be unaffected at flag={value}"
        )


# ── the trap: why this fix does NOT touch the splitter ─────────────────
#
# The obvious companion fix — make ``_is_multi_phrase`` abbreviation-aware
# so a user-typed "Art. 13" stops false-firing — is a trap, and these tests
# pin the evidence so nobody "completes" the fix later and regresses it.

@pytest.mark.parametrize("article", [5, 6, 13, 50, 99, 113])
def test_real_sentence_boundary_after_article_cite_still_fires(
    monkeypatch, article
):
    """The blocker that killed the abbreviation-aware-splitter approach.

    ``split_legal_sentences`` glues "… Art. 13. Must we …" — its
    ``_NUMBERED_LIST_RE`` (``\\d{1,3}\\.$``) reads the trailing "13." as a
    paragraph marker — so a genuine two-sentence question collapses to ONE
    segment and silently downgrades to the weaker tier. Measured at 113/113
    article numbers.

    This is a NON-REGRESSION guard on the naive splitter we deliberately
    kept: these questions must stay complex. Direct on ``_is_multi_phrase``
    so no other category regex can mask the signal (the earlier version of
    this guard was vacuous for exactly that reason).
    """
    m = _reload(monkeypatch, "1")
    q = (
        f"We inform users of the chatbot under Art. {article}. "
        "Must we also register the system in the EU database?"
    )
    assert m._is_multi_phrase(q) is True, (
        f"Art. {article}. at a real sentence end must still read as 2 phrases"
    )


def test_real_sentence_boundary_after_annex_cite_still_fires(monkeypatch):
    """The mirror trap in the OTHER candidate splitter.

    ``tone_guard._SENTENCE_SPLIT`` fixes ``Art. N.`` but glues
    "… Annex III. Must we …" via its ``(?<!\\bAnnex III)`` lookbehind. Both
    splitters are correct for the legal PROSE they were written for and
    wrong for a question. Pinned so a future "just reuse tone_guard" also
    fails loudly here.
    """
    m = _reload(monkeypatch, "1")
    q = (
        "The system is listed in Annex III. "
        "Must we also register it in the EU database?"
    )
    assert m._is_multi_phrase(q) is True


def test_user_typed_abbreviation_false_fire_is_accepted(monkeypatch):
    """Documents a KNOWN, deliberately-unfixed false positive.

    A user typing "Art. 13" mid-sentence still reads as two phrases and
    over-routes to the complex tier. That costs LATENCY only (both tiers
    are the same model; they differ by thinking budget), whereas every
    available fix costs a false MISS on the tests above — answer
    correctness. Cheap error kept, expensive error avoided.

    If a question-appropriate splitter ever lands, delete this test.
    """
    m = _reload(monkeypatch, "1")
    q = (
        "The provider must comply with Art. 13 and disclose all required "
        "information to users."
    )
    assert m._is_multi_phrase(q) is True, "known over-fire, accepted"


# ── the expensive failure mode: do NOT over-correct ─────────────────────

@pytest.mark.parametrize(
    "question",
    [
        "What is a deployer? What is a provider?",
        "We deploy a hiring model in France. Our vendor rebrands it under "
        "our logo.",
    ],
)
def test_genuine_multi_phrase_still_fires(monkeypatch, question):
    """Regression guard on the EXPENSIVE direction.

    A false NEGATIVE downgrades a genuinely-complex question to the weaker
    tier — that costs answer correctness, not just latency.

    Asserted on ``_is_multi_phrase`` DIRECTLY, not through
    ``is_complex_question``: the earlier version of this guard went through
    the public entry point, where ``_ROLE_AMBIGUITY_RE`` matched
    "rebrands" and returned True before the multi-phrase signal was ever
    reached — so the guard passed green against a live blocker-level
    regression in the very signal it claimed to protect.
    """
    m = _reload(monkeypatch, "1")
    assert m._is_multi_phrase(question) is True


def test_two_questions_signal_is_independent_of_the_strip(monkeypatch):
    """The ``?``-count signal must be unaffected by the anchor strip."""
    m = _reload(monkeypatch, "1")
    assert m._is_multi_phrase("What is X? What is Y?") is True


# ── the SECOND, mirror-image bug the prefix caused ─────────────────────

def test_anchor_prefix_no_longer_suppresses_short_coreferent_signal(
    monkeypatch,
):
    """The anchor prefix ALSO suppressed a signal that SHOULD fire.

    ``_SHORT_COREFERENT_RE`` is ``^``-anchored. On the marker-less denoised
    path the injected prefix sat at position 0, so the anchor could never
    match and a genuine short coreferent follow-up ("And for Annex I …?")
    was silently DOWNGRADED to the weaker tier — a correctness cost, the
    expensive direction.

    Same root cause as the ``Art.`` bug (we scanned our own metadata as if
    it were user text) but the opposite sign, which is why the fix is not
    a pure latency play. Real row: ``mt_v2:mt_v2_019`` in the ab_judge
    probe set flips False→True under the fix.
    """
    anchor = "[Context anchors — articles: Annex III; risk tier: annex i, annex iii]"
    live = "And for Annex I (medical devices etc.) embedded systems?"

    off = _reload(monkeypatch, "0")
    assert off.is_complex_question(f"{anchor}\n{live}", 3) is False, (
        "baseline: the prefix suppresses the short-coreferent signal"
    )

    on = _reload(monkeypatch, "1")
    assert on.is_complex_question(f"{anchor}\n{live}", 3) is True, (
        "fixed: a short coreferent follow-up reaches the complex tier"
    )
    assert on.is_complex_question(f"{anchor}\n{live}", 3) == on.is_complex_question(
        live, 3
    ), "tier must not depend on metadata we injected"


# ── the flag contract ──────────────────────────────────────────────────

def test_flag_defaults_on(monkeypatch):
    monkeypatch.delenv("REGENOLD_COMPLEXITY_ABBREV_FIX", raising=False)
    m = importlib.reload(qc)
    assert m._anchor_strip_enabled() is True, "R276-D2 ships default ON"


def test_flag_is_in_engine_cache_key():
    """R30/R56/R79/R263.2 cache-poisoning doctrine.

    The flag flips the Stage-2 tier ⇒ flips ``GraphRAGResponse.answer``,
    which is what this cache stores. If it is not in the key, an in-process
    A/B (``ab_judge`` toggles env between arms) serves the baseline arm's
    answer to the branch arm and silently reports a wash — exactly the
    R263.2 failure. Asserted against source so the flag cannot be dropped
    from the tuple during a merge.
    """
    src = pathlib.Path("app/routes/regenold.py").read_text(encoding="utf-8")
    key_fn = src.split("def _engine_cache_key")[1].split("\ndef ")[0]
    assert "REGENOLD_COMPLEXITY_ABBREV_FIX" in key_fn


# ── the bench gate's own assumption ────────────────────────────────────

def test_davidath_corpus_is_tier_identical_under_the_fix(monkeypatch):
    """The ``--assert-baseline`` gate expects byte-identity.

    The R276 plan justified that with "davidath is single-turn ⇒ no
    context-anchor prefix" — insufficient, since the abbreviation half also
    fires on single-turn text. The real reason is measured here: no davidath
    row crosses the multi-phrase threshold in either direction. Pinned so a
    corpus refresh that ADDS such a row fails loudly here rather than as a
    mystery byte-identity break.
    """
    path = pathlib.Path("evals/bench/data/qa_pairs.json")
    if not path.exists():  # dataset not vendored in this checkout
        pytest.skip("davidath qa_pairs.json not present")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else next(
        v for v in raw.values() if isinstance(v, list)
    )
    questions = [
        r.get("question") or r.get("q") or ""
        for r in rows
        if isinstance(r, dict)
    ]
    assert questions, "corpus parsed empty — the guard would be vacuous"

    off = _reload(monkeypatch, "0")
    baseline = [off.is_complex_question(q, 1) for q in questions]
    on = _reload(monkeypatch, "1")
    branch = [on.is_complex_question(q, 1) for q in questions]

    flipped = [
        q
        for q, a, b in zip(questions, baseline, branch, strict=True)
        if a != b
    ]
    assert not flipped, (
        f"{len(flipped)} davidath row(s) change tier under R276-D2 — the "
        f"bench byte-identity gate will break: {flipped[:3]}"
    )
