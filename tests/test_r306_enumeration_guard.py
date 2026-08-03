"""R306 — enumeration-span guard regression tests.

THE DEFECT (measured on the live production wire, 2026-08-03):

    Q: "Under the EU AI Act, what are the four grounds on which
        non-compliance with the Act may be alleged (as listed in
        Article 79(6))?"
    Production shipped, on two independent runs:
        277 chars -> announced "four grounds", delivered (a) only
        363 chars -> announced "four grounds", delivered (a) and (b)
    The same question run in-process with the sentence cap lifted
    returns all four grounds (1389 chars).

    Q: "What are the deployer obligations under Art 50"
    Production: 464 chars, announced "three transparency obligations",
    delivered two.

ROOT CAUSE. ``normalise_answer_for_regenold`` caps at ``max_sentences``
and, when over the char budget, drops the longest non-citation-bearing
sentence. Both passes are blind to enumeration structure. The existing
escapes that lift the cap (``_is_closed_set_enumeration_ask``,
``_is_multi_phrase``, ``is_complex_question``) all inspect the QUESTION
and all return False for both questions above.

THE GUARD reads the ANSWER instead: a run of >= 2 consecutively
labelled items must not be cut. Every test below uses the VERBATIM
production question / answer shape, never an abbreviation (the R305
review found an R304 test that passed only because it asserted on a
truncated copy of its own target question).
"""

from __future__ import annotations

import importlib

import pytest

from app.integrations.regenold.answer_normaliser import (
    answer_has_enumeration,
    enumeration_guard_enabled,
    enumeration_run_end,
    enumeration_run_indices,
    inline_enumeration_length,
)
from app.integrations.regenold.models import (
    _split_sentences,
    normalise_answer_for_regenold,
)

# ── Verbatim reproductions of the live defect ────────────────────────

Q_ART50 = "What are the deployer obligations under Art 50"
Q_ART79 = (
    "Under the EU AI Act, what are the four grounds on which "
    "non-compliance with the Act may be alleged (as listed in "
    "Article 79(6))?"
)

# The complete answer the SAME commit returns in-process with the cap
# lifted. Production truncates this to its first three sentences.
A_ART50_FULL = (
    "Article 50 imposes three transparency obligations on deployers. "
    "First, under Article 50(3), deployers operating emotion recognition "
    "or biometric categorisation systems must inform the natural persons "
    "exposed to those systems. "
    "Second, under Article 50(4), deployers must label deepfakes, that is, "
    "AI-generated or manipulated image, audio, or video content, as "
    "artificially generated or manipulated. "
    "Third, also under Article 50(4), deployers who use an AI system to "
    "generate or manipulate text that is published to inform the public on "
    "matters of public interest must disclose that the text was "
    "artificially generated or manipulated. "
    "Two carve-outs narrow the Article 50(4) disclosure duty. "
    "The obligation does not apply where the use is authorised by law to "
    "detect, prevent, investigate, or prosecute criminal offences. "
    "It also does not apply where the content has undergone human review "
    "or editorial control."
)

A_ART79_FULL = (
    "Article 79(6) requires market surveillance authorities, when "
    "notifying non-compliance, to indicate whether the non-compliance is "
    "due to one or more of the following four grounds. "
    "(a) Non-compliance with the prohibition of the AI practices referred "
    "to in Article 5. "
    "(b) A failure of a high-risk AI system to meet the requirements set "
    "out in Chapter III, Section 2. "
    "(c) Shortcomings in the harmonised standards or common "
    "specifications referred to in Articles 40 and 41. "
    "(d) Non-compliance with Article 50."
)

# A non-enumerated multi-sentence answer. The guard MUST leave this
# alone: Answer-Conciseness is the one rubric axis this system leads.
A_PLAIN = (
    "Article 26 requires deployers to use high-risk AI systems in "
    "accordance with the instructions for use. "
    "They must assign human oversight to competent natural persons. "
    "They must keep the automatically generated logs. "
    "They must inform the provider of any serious incident. "
    "Market surveillance authorities may request those logs."
)


@pytest.fixture()
def prod_cap(monkeypatch):
    """Pin the cap configuration production demonstrably runs.

    Derived, not assumed: across 120 recorded production rows, an answer
    exceeds three sentences if and only if a question-side escape gate
    fires (118/120; the 2 exceptions are the same multi-turn row scored
    on its unflattened question). That is the signature of the default
    ``MAX_ANSWER_SENTENCES`` of 3, i.e. railway.toml's ``="0"`` is not
    reaching the service.
    """
    monkeypatch.setenv("REGENOLD_MAX_ANSWER_SENTENCES", "3")
    monkeypatch.setenv("REGENOLD_HARD_CHAR_CAP", "0")
    monkeypatch.setenv("REGENOLD_QA_LENGTH_CAP", "1200")


# ── The detector itself ──────────────────────────────────────────────


class TestEnumerationDetector:
    def test_ordinal_run_detected(self):
        sentences = _split_sentences(A_ART50_FULL)
        idxs = enumeration_run_indices(sentences)
        # First / Second / Third are sentences 1, 2, 3 (0-based).
        assert idxs == {1, 2, 3}
        assert enumeration_run_end(sentences) == 4

    def test_lettered_run_detected(self):
        sentences = _split_sentences(A_ART79_FULL)
        idxs = enumeration_run_indices(sentences)
        assert len(idxs) == 4, f"expected (a)-(d), got {sorted(idxs)}"
        assert enumeration_run_end(sentences) == len(sentences)

    def test_plain_prose_has_no_run(self):
        assert enumeration_run_indices(_split_sentences(A_PLAIN)) == set()
        assert enumeration_run_end(_split_sentences(A_PLAIN)) == 0

    def test_single_marker_is_not_a_run(self):
        """A lone illustrative "(g)" must not trip the guard."""
        text = (
            "Article 5 bans eight categories of AI practice. "
            "(g) biometric categorisation by sensitive attributes is one of them."
        )
        assert enumeration_run_indices(_split_sentences(text)) == set()

    def test_non_consecutive_markers_are_not_a_run(self):
        """Items must ascend by one; (a) then (c) is not a detected run."""
        sentences = ["(a) First ground here.", "(c) Third ground here."]
        assert enumeration_run_indices(sentences) == set()

    def test_ordinal_requires_delimiter(self):
        """Ordinary prose that merely opens with an ordinal word."""
        sentences = [
            "First instance courts apply the Regulation directly.",
            "Second hand data may still be personal data.",
        ]
        assert enumeration_run_indices(sentences) == set()

    def test_year_is_not_a_numbered_item(self):
        sentences = ["2024 saw the Regulation adopted.", "2026 brings the next phase."]
        assert enumeration_run_indices(sentences) == set()

    def test_run_end_is_clamped(self):
        sentences = [f"({chr(96 + i)}) Ground number {i}." for i in range(1, 11)]
        # 10 consecutive items, ceiling is 12 -> uncapped here, but the
        # clamp must never exceed 12.
        assert enumeration_run_end(sentences) <= 12

    def test_detector_is_pure(self):
        sentences = _split_sentences(A_ART79_FULL)
        before = list(sentences)
        enumeration_run_indices(sentences)
        enumeration_run_end(sentences)
        assert sentences == before

    def test_empty_input_is_safe(self):
        assert enumeration_run_indices([]) == set()
        assert enumeration_run_end([]) == 0


# ── Inline lists: one sentence, shredded by the OTHER caps ───────────

# The same four grounds written inline. ``_split_sentences`` returns ONE
# sentence for this, so the sentence-cap floor never sees it; it dies
# instead to the route's readable-unit cap (each "(x)" clause counts as
# a unit) and to ``_hard_truncate_at_clause`` (which truncates AT an
# enumerator boundary). A guard that only patches the sentence cap
# fixes half the defect.
A_ART79_INLINE = (
    "Article 79(6) requires the authority to indicate whether the "
    "non-compliance is due to one or more of the following four grounds: "
    "(a) non-compliance with the prohibition of the AI practices referred "
    "to in Article 5; "
    "(b) a failure of a high-risk AI system to meet the requirements set "
    "out in Chapter III, Section 2; "
    "(c) shortcomings in the harmonised standards or common specifications "
    "referred to in Articles 40 and 41; or "
    "(d) non-compliance with Article 50."
)


class TestInlineEnumeration:
    def test_inline_run_detected(self):
        assert inline_enumeration_length(A_ART79_INLINE) == 4
        assert answer_has_enumeration(A_ART79_INLINE) is True

    def test_inline_list_is_one_sentence(self):
        """Pins WHY a sentence-cap-only guard would miss this shape."""
        assert len(_split_sentences(A_ART79_INLINE)) == 1
        assert enumeration_run_end(_split_sentences(A_ART79_INLINE)) == 0

    def test_readable_unit_cap_would_shred_it(self):
        """The route cap this guard now relaxes really does cut the list."""
        from app.integrations.regenold.models import _cap_readable_units

        capped = _cap_readable_units(A_ART79_INLINE, max_units=4)
        assert "(d)" not in capped, "expected the unguarded cap to drop a member"

    def test_multi_sentence_shape_also_detected(self):
        assert answer_has_enumeration(A_ART79_FULL) is True
        assert answer_has_enumeration(A_ART50_FULL) is True

    def test_plain_prose_not_detected(self):
        assert answer_has_enumeration(A_PLAIN) is False

    def test_single_illustrative_marker_not_detected(self):
        """rule 12 licenses "Article 5 bans eight practices, including (g)…"."""
        text = (
            "Article 5 bans eight categories of AI practice. "
            "Point (g) covers biometric categorisation by sensitive attributes."
        )
        assert inline_enumeration_length(text) == 0
        assert answer_has_enumeration(text) is False

    def test_non_consecutive_inline_markers_not_detected(self):
        text = "See point (a) of Article 5 and point (h) of the same paragraph."
        assert inline_enumeration_length(text) == 0

    def test_inline_detector_respects_off_switch(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "0")
        assert answer_has_enumeration(A_ART79_INLINE) is False

    def test_inline_detector_is_fail_soft(self):
        for bad in ("", None, 12345, "(a)" * 2000):
            try:
                inline_enumeration_length(bad)  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover
                pytest.fail(f"raised on {bad!r}: {exc}")


# ── The wire behaviour: the actual defect ────────────────────────────


class TestGuardFixesTheLiveDefect:
    def test_art79_four_grounds_all_delivered(self, prod_cap, monkeypatch):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        out = normalise_answer_for_regenold(A_ART79_FULL, None, Q_ART79)
        for item in ("(a)", "(b)", "(c)", "(d)"):
            assert item in out, f"ground {item} dropped from: {out!r}"

    def test_art79_without_guard_reproduces_the_defect(self, prod_cap, monkeypatch):
        """Pin the defect so a future change cannot silently reintroduce it."""
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "0")
        out = normalise_answer_for_regenold(A_ART79_FULL, None, Q_ART79)
        assert "four grounds" in out
        assert "(d)" not in out, "baseline should still truncate"

    def test_art50_third_obligation_delivered(self, prod_cap, monkeypatch):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        out = normalise_answer_for_regenold(A_ART50_FULL, None, Q_ART50)
        assert "Third," in out, f"third obligation dropped from: {out!r}"

    def test_announced_count_matches_delivered_items(self, prod_cap, monkeypatch):
        """The self-contradiction the judge names 'promised-but-undelivered'."""
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        out = normalise_answer_for_regenold(A_ART50_FULL, None, Q_ART50)
        assert "three transparency obligations" in out
        delivered = sum(1 for w in ("First,", "Second,", "Third,") if w in out)
        assert delivered == 3, f"announced three, delivered {delivered}: {out!r}"


# ── Bounded-ness: the conciseness guarantee ──────────────────────────


class TestGuardIsBounded:
    def test_non_enumerated_answer_is_byte_identical(self, prod_cap, monkeypatch):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "0")
        off = normalise_answer_for_regenold(A_PLAIN, None, "What must deployers do?")
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        on = normalise_answer_for_regenold(A_PLAIN, None, "What must deployers do?")
        assert off == on

    def test_trailing_commentary_after_the_run_is_still_trimmed(
        self, prod_cap, monkeypatch
    ):
        """The guard protects the LIST, not the whole answer.

        Answer-Conciseness is the only rubric axis this system leads, so
        the guard must not become a blank cheque: everything after the
        enumeration run stays trimmable.
        """
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        out = normalise_answer_for_regenold(A_ART50_FULL, None, Q_ART50)
        assert "Third," in out
        assert len(out) < len(A_ART50_FULL), (
            "guard must still trim the post-enumeration tail"
        )

    def test_guard_never_shortens_an_answer(self, prod_cap, monkeypatch):
        """Additive-only: it may raise a cap, never lower one."""
        for text, question in (
            (A_ART50_FULL, Q_ART50),
            (A_ART79_FULL, Q_ART79),
            (A_PLAIN, "What must deployers do?"),
        ):
            monkeypatch.setenv("REGENOLD_ENUM_GUARD", "0")
            off = normalise_answer_for_regenold(text, None, question)
            monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
            on = normalise_answer_for_regenold(text, None, question)
            assert len(on) >= len(off)

    def test_guard_adds_no_content(self, prod_cap, monkeypatch):
        """No fabrication surface: every word shipped was in the input."""
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        out = normalise_answer_for_regenold(A_ART79_FULL, None, Q_ART79)
        for token in ("Shortcomings", "harmonised", "Section 2"):
            assert token in A_ART79_FULL
        # Every alphabetic token on the wire came from the source text.
        src = set(A_ART79_FULL.lower().split())
        for tok in out.lower().split():
            stripped = tok.strip(".,;:()")
            if stripped and stripped.isalpha():
                assert any(stripped in s for s in src), f"invented token {tok!r}"


# ── Env gate, idempotence, fail-soft ─────────────────────────────────


class TestGuardContract:
    def test_default_is_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_ENUM_GUARD", raising=False)
        assert enumeration_guard_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF", " 0 "])
    def test_off_switch(self, monkeypatch, value):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", value)
        assert enumeration_guard_enabled() is False
        assert enumeration_run_end(_split_sentences(A_ART79_FULL)) == 0

    def test_idempotent(self, prod_cap, monkeypatch):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        once = normalise_answer_for_regenold(A_ART79_FULL, None, Q_ART79)
        twice = normalise_answer_for_regenold(once, None, Q_ART79)
        assert twice == once

    def test_no_cap_path_unaffected(self, monkeypatch):
        """With the cap disabled the guard is a no-op, not a second cap."""
        monkeypatch.setenv("REGENOLD_MAX_ANSWER_SENTENCES", "0")
        monkeypatch.setenv("REGENOLD_HARD_CHAR_CAP", "0")
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "0")
        off = normalise_answer_for_regenold(A_ART79_FULL, None, Q_ART79)
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        on = normalise_answer_for_regenold(A_ART79_FULL, None, Q_ART79)
        assert off == on

    def test_fail_soft_on_pathological_input(self, prod_cap, monkeypatch):
        monkeypatch.setenv("REGENOLD_ENUM_GUARD", "1")
        for text in ("", "   ", "(a)", "First,", "a" * 5000):
            normalise_answer_for_regenold(text, None, Q_ART79)  # must not raise

    def test_module_reload_is_clean(self):
        import app.integrations.regenold.answer_normaliser as an

        importlib.reload(an)
        assert callable(an.enumeration_run_end)


# ── davidath neutrality, asserted not assumed ────────────────────────


class TestDavidathNeutrality:
    def test_guard_fires_on_no_davidath_row(self):
        """Measured: 0 of 476 davidath rows carry an enumeration run.

        The davidath answers come from the deterministic KB-stub
        composer, which writes flowing prose and never emits
        "First,"/"(a)" item markers. This is the structural reason the
        full 476-row A/B is byte-identical; pinning it here means a
        future KB edit that starts emitting lists shows up as a test
        failure rather than a silent bench movement.
        """
        from evals.bench.dataset import load_qa_pairs, load_scenarios

        try:
            rows = list(load_qa_pairs()) + list(load_scenarios())
        except Exception:  # pragma: no cover - offline CI
            pytest.skip("davidath dataset unavailable offline")

        assert len(rows) == 476, f"expected the 137+339 davidath set, got {len(rows)}"
        fired = []
        for row in rows:
            for key in ("answer", "gold_answer", "expected_answer"):
                gold = row.get(key)
                if isinstance(gold, str) and gold:
                    if enumeration_run_indices(_split_sentences(gold)):
                        fired.append((row.get("id"), key))
                    break
        assert not fired, f"davidath gold answers now enumerate: {fired[:5]}"
